import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 应用设置：后端地址等（用户可在设置页修改，持久化到本地）。
class SettingsService {
  static const String _apiKey = 'api_base_url';

  final SharedPreferences prefs;

  /// 后端地址变化时通知监听方（首页）立即刷新。
  final ValueNotifier<String> apiBaseUrl;

  SettingsService(this.prefs)
      : apiBaseUrl = ValueNotifier<String>(prefs.getString(_apiKey) ?? '');

  bool get isConfigured => apiBaseUrl.value.trim().isNotEmpty;

  Future<void> setApiBaseUrl(String url) async {
    final normalized = _normalize(url);
    await prefs.setString(_apiKey, normalized);
    apiBaseUrl.value = normalized;
  }

  /// 去空白、补协议前缀、去末尾斜杠。
  String _normalize(String url) {
    var u = url.trim();
    if (u.isEmpty) return '';
    if (!u.startsWith('http://') && !u.startsWith('https://')) {
      u = 'http://$u';
    }
    while (u.endsWith('/')) {
      u = u.substring(0, u.length - 1);
    }
    return u;
  }
}
