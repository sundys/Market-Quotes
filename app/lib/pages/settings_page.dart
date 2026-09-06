import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:open_filex/open_filex.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../services/settings_service.dart';
import '../services/update_service.dart';
import '../theme/app_colors.dart';

/// 极简设置页：检测更新 + 后端地址录入 + 数据来源说明（AGENTS.md 第 40 节）。
class SettingsPage extends StatefulWidget {
  final SettingsService settings;
  final UpdateService updateService;

  const SettingsPage({super.key, required this.settings, required this.updateService});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late final TextEditingController _urlController;
  String _version = '';
  String _updateState = '';
  bool _checking = false;
  bool _downloading = false;

  @override
  void initState() {
    super.initState();
    _urlController = TextEditingController(text: widget.settings.apiBaseUrl.value);
    PackageInfo.fromPlatform().then((info) {
      if (mounted) setState(() => _version = 'v${info.version}');
    });
    // 进入设置页自动检测一次更新（静默，发现新版本才弹窗）
    WidgetsBinding.instance.addPostFrameCallback((_) => _checkUpdate(manual: false));
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  /// 检测更新：发现新版本弹窗提示，确认后下载（多代理）并调起安装。
  Future<void> _checkUpdate({required bool manual}) async {
    if (_checking) return;
    setState(() {
      _checking = true;
      _updateState = '检查更新中…';
    });
    final update = await widget.updateService.checkLatest();
    if (!mounted) return;
    setState(() => _checking = false);

    if (update == null) {
      setState(() => _updateState = '检查失败');
      if (manual) _showSnack('检查失败：所有更新源均不可达', error: true);
      return;
    }

    final info = await PackageInfo.fromPlatform();
    final isNewer = UpdateService.compareVersions(update.version, info.version) > 0;
    if (!mounted) return;
    if (!isNewer) {
      setState(() => _updateState = '已是最新 v${info.version}');
      if (manual) _showSnack('已是最新版本 v${info.version}');
      return;
    }

    setState(() => _updateState = '发现新版本 v${update.version}');
    _showUpdateDialog(update);
  }

  Future<void> _showUpdateDialog(AppUpdate update) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: Text('发现新版本 ${update.version}',
            style: const TextStyle(
                color: AppColors.textPrimary, fontWeight: FontWeight.w700, fontSize: 18)),
        content: SizedBox(
          width: 300,
          child: SingleChildScrollView(
            child: Text(
              update.body.trim().isEmpty ? '修复若干问题，体验更佳。' : update.body.trim(),
              style: const TextStyle(color: AppColors.textSecondary, fontSize: 13.5, height: 1.5),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('稍后再说', style: TextStyle(color: AppColors.textSecondary)),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.primary,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('下载安装'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    _downloadAndInstall(update);
  }

  Future<void> _downloadAndInstall(AppUpdate update) async {
    setState(() {
      _downloading = true;
      _updateState = '准备下载…';
    });
    final progress = ValueNotifier<double>(0);
    var dialogOpen = false;

    // 进度弹窗（不可关闭）
    Future<void> openProgressDialog() async {
      dialogOpen = true;
      await showDialog(
        context: context,
        barrierDismissible: false,
        builder: (context) => PopScope(
          canPop: false,
          child: ValueListenableBuilder<double>(
            valueListenable: progress,
            builder: (context, value, _) => AlertDialog(
              backgroundColor: AppColors.surface,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
              title: const Text('正在下载更新',
                  style: TextStyle(
                      color: AppColors.textPrimary, fontWeight: FontWeight.w700, fontSize: 17)),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: LinearProgressIndicator(
                      value: value > 0 ? value : null,
                      minHeight: 8,
                      backgroundColor: AppColors.divider,
                      color: AppColors.primary,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    value > 0 ? '${(value * 100).toStringAsFixed(0)}%' : '连接下载源…',
                    style: const TextStyle(color: AppColors.textSecondary, fontSize: 12.5),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    }

    // 异步打开进度弹窗（不影响下载流程）
    if (mounted) {
      openProgressDialog();
      // 等待弹窗真正入栈
      await Future.delayed(const Duration(milliseconds: 150));
    }

    String? apkPath;
    try {
      String abis = 'arm64-v8a';
      try {
        final info = await DeviceInfoPlugin().androidInfo;
        abis = info.supportedAbis.isNotEmpty ? info.supportedAbis.first : 'arm64-v8a';
      } catch (_) {}
      final assetName = UpdateService.assetForAbis([abis]);
      final file = await widget.updateService.downloadApk(
        update: update,
        assetName: assetName,
        progress: progress,
      );
      apkPath = file.path;
    } catch (e) {
      apkPath = null;
      if (mounted) _showSnack('下载失败：$e', error: true);
    } finally {
      if (mounted && dialogOpen) Navigator.of(context, rootNavigator: true).pop();
      if (mounted) {
        setState(() {
          _downloading = false;
          _updateState = apkPath != null ? '已下载，正在安装' : '下载失败';
        });
      }
    }

    if (apkPath == null || !mounted) return;
    // 调起系统安装器（若未授予"安装未知应用"权限会跳转授权页）
    final result = await OpenFilex.open(apkPath);
    if (!mounted) return;
    if (result.type != ResultType.done) {
      _showSnack('无法启动安装：${result.message}。请在系统设置中允许本应用安装未知应用。', error: true);
    }
  }

  Future<void> _save() async {    final url = _urlController.text.trim();
    if (url.isNotEmpty && !Uri.tryParse(url)!.hasScheme) {
      // _normalize 会补 http://，这里只拦真正非法的输入
      _showSnack('地址格式不正确', error: true);
      return;
    }
    await widget.settings.setApiBaseUrl(url);
    if (!mounted) return;
    _showSnack('已保存');
  }

  void _showSnack(String message, {bool error = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: error ? AppColors.negative : AppColors.surfaceDark,
        duration: const Duration(seconds: 2),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text(
          '设置',
          style: TextStyle(color: AppColors.textPrimary, fontWeight: FontWeight.w700),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          _group(
            title: '版本更新',
            children: [
              _UpdateTile(
                stateText: _updateState,
                checking: _checking,
                onTap: _checking || _downloading ? null : () => _checkUpdate(manual: true),
              ),
            ],
          ),
          const SizedBox(height: 20),
          _group(
            title: '后端地址',
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                child: TextField(
                  controller: _urlController,
                  keyboardType: TextInputType.url,
                  inputFormatters: [FilteringTextInputFormatter.singleLineFormatter],
                  decoration: const InputDecoration(
                    hintText: '例如：http://192.168.1.10:8000',
                    border: InputBorder.none,
                    hintStyle: TextStyle(color: AppColors.textSecondary, fontSize: 14),
                  ),
                  style: const TextStyle(fontSize: 14.5, color: AppColors.textPrimary),
                ),
              ),
              const Padding(
                padding: EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: Text(
                  '填写你自己部署的后端服务地址，保存后立即生效',
                  style: TextStyle(color: AppColors.textSecondary, fontSize: 12),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
                child: Row(
                  children: [
                    Expanded(
                      child: FilledButton.icon(
                        onPressed: _save,
                        style: FilledButton.styleFrom(
                          backgroundColor: AppColors.primary,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14),
                          ),
                        ),
                        icon: const Icon(Icons.save_outlined, size: 18),
                        label: const Text('保存'),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          _group(
            title: '数据来源',
            children: const [
              _InfoTile(
                title: '国际黄金 / 纳斯达克100 / 标普500',
                subtitle: 'Yahoo Finance · 数据有一定延迟，仅供参考',
              ),
              _InfoTile(
                title: '上海黄金 Au99.99',
                subtitle: '上海黄金交易所（经 AKShare 获取）',
              ),
            ],
          ),
          const SizedBox(height: 20),
          _group(
            title: '关于',
            children: [
              _InfoTile(title: '版本', subtitle: _version.isEmpty ? '…' : _version),
              const _InfoTile(
                title: '免责声明',
                subtitle: '本应用仅展示行情，不提供任何交易功能；价格可能延迟，不构成投资建议。',
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _group({required String title, required List<Widget> children}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 8),
          child: Text(
            title,
            style: const TextStyle(
              color: AppColors.textSecondary,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        Container(
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(20),
          ),
          child: Column(children: children),
        ),
      ],
    );
  }
}

class _InfoTile extends StatelessWidget {
  final String title;
  final String subtitle;

  const _InfoTile({required this.title, required this.subtitle});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: AppColors.textPrimary,
              fontSize: 15,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 3),
          Text(
            subtitle,
            style: const TextStyle(color: AppColors.textSecondary, fontSize: 12.5),
          ),
        ],
      ),
    );
  }
}

/// 检测更新入口。
class _UpdateTile extends StatelessWidget {
  final String stateText;
  final bool checking;
  final VoidCallback? onTap;

  const _UpdateTile({required this.stateText, required this.checking, this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '检测更新',
                    style: TextStyle(
                      color: AppColors.textPrimary,
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (stateText.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(
                      stateText,
                      style: const TextStyle(color: AppColors.textSecondary, fontSize: 12.5),
                    ),
                  ],
                ],
              ),
            ),
            checking
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.arrow_forward_ios, size: 15, color: AppColors.textSecondary),
          ],
        ),
      ),
    );
  }
}
