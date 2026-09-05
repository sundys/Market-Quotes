import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/settings_service.dart';
import '../theme/app_colors.dart';

/// 极简设置页：后端地址录入 + 数据来源说明（AGENTS.md 第 40 节）。
class SettingsPage extends StatefulWidget {
  final SettingsService settings;

  const SettingsPage({super.key, required this.settings});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late final TextEditingController _urlController;

  @override
  void initState() {
    super.initState();
    _urlController = TextEditingController(text: widget.settings.apiBaseUrl.value);
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final url = _urlController.text.trim();
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
            children: const [
              _InfoTile(title: '版本', subtitle: 'v1.0.0'),
              _InfoTile(
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
