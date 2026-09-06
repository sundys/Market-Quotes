import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

/// 应用内更新：GitHub Release 检测 + 多代理下载。
///
/// 直连 GitHub 在大陆网络不可靠，因此检测与下载都按镜像列表依次尝试；
/// 任一源失败自动切换下一个，避免单一代理失效导致无法更新。
class UpdateService {
  static const String _owner = 'sundys';
  static const String _repo = 'Market-Quotes';
  static const String _assetArm64 = 'app-arm64-v8a-release.apk';
  static const String _assetArmv7 = 'app-armeabi-v7a-release.apk';

  /// 下载/检测镜像：空串表示 GitHub 直连，其余为前缀代理（拼完整 URL）。
  /// 顺序即优先级；若代理失效请在此追加新的前缀即可。
  static const List<String> _mirrors = [
    '',
    'https://ghfast.top/',
    'https://gh-proxy.com/',
    'https://ghproxy.net/',
    'https://hub.gitmirror.com/',
  ];

  /// 获取最新版本信息；全部源失败返回 null。
  Future<AppUpdate?> checkLatest({String assetName = _assetArm64}) async {
    for (final mirror in _mirrors) {
      try {
        final resp = await http
            .get(
              Uri.parse(
                  '${mirror}https://api.github.com/repos/$_owner/$_repo/releases/latest'),
              headers: const {'User-Agent': 'Mozilla/5.0'},
            )
            .timeout(const Duration(seconds: 10));
        if (resp.statusCode != 200) continue;
        final body = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
        final tag = body['tag_name'] as String? ?? '';
        if (tag.isEmpty) continue;
        final assets = <String, String>{};
        for (final a in (body['assets'] as List? ?? const [])) {
          final name = a['name'] as String? ?? '';
          final url = a['browser_download_url'] as String? ?? '';
          if (name.isNotEmpty && url.isNotEmpty) assets[name] = url;
        }
        return AppUpdate(
          tag: tag,
          version: tag.startsWith('v') ? tag.substring(1) : tag,
          body: body['body'] as String? ?? '',
          assetUrls: assets,
        );
      } catch (_) {
        continue; // 尝试下一个镜像
      }
    }
    return null;
  }

  /// 下载指定 APK；依次尝试直连与各代理，失败自动切换。
  /// progress 为 0.0~1.0（部分源无长度时保持 0）。
  Future<File> downloadApk({
    required AppUpdate update,
    required String assetName,
    required ValueNotifier<double> progress,
    http.Client? client,
  }) async {
    final url = update.assetUrls[assetName];
    if (url == null || url.isEmpty) {
      throw Exception('更新包不存在: $assetName');
    }
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/$assetName');
    final httpClient = client ?? http.Client();

    for (final mirror in _mirrors) {
      try {
        progress.value = 0;
        final request = http.Request('GET', Uri.parse('$mirror$url'));
        request.headers['User-Agent'] = 'Mozilla/5.0';
        final response =
            await httpClient.send(request).timeout(const Duration(seconds: 30));
        if (response.statusCode != 200) continue;

        final total = response.contentLength ?? 0;
        final sink = file.openWrite();
        var received = 0;
        try {
          await for (final chunk in response.stream) {
            received += chunk.length;
            sink.add(chunk);
            if (total > 0) progress.value = received / total;
          }
          await sink.flush();
        } finally {
          await sink.close();
        }
        if (total > 0 && received < total) {
          throw Exception('下载不完整 ($received/$total)');
        }
        return file;
      } catch (_) {
        progress.value = 0;
        continue; // 尝试下一个镜像
      }
    }
    throw Exception('所有下载源均失败，请稍后重试');
  }

  /// 版本号比较：>0 表示 a 更新，<0 表示 b 更新，0 相同。忽略非数字部分。
  static int compareVersions(String a, String b) {
    List<int> parse(String v) => v
        .replaceFirst(RegExp(r'^[vV]'), '')
        .split('.')
        .map((s) => int.tryParse(s) ?? 0)
        .toList();
    final pa = parse(a), pb = parse(b);
    final n = pa.length > pb.length ? pa.length : pb.length;
    for (var i = 0; i < n; i++) {
      final x = i < pa.length ? pa[i] : 0;
      final y = i < pb.length ? pb[i] : 0;
      if (x != y) return x.compareTo(y);
    }
    return 0;
  }

  /// 根据设备 ABI 选择安装包名。
  static String assetForAbis(List<String> abis) {
    return abis.contains('arm64-v8a') ? _assetArm64 : _assetArmv7;
  }
}

/// 一次版本检查的结果。
class AppUpdate {
  final String tag;
  final String version;
  final String body;
  final Map<String, String> assetUrls;

  const AppUpdate({
    required this.tag,
    required this.version,
    required this.body,
    required this.assetUrls,
  });
}
