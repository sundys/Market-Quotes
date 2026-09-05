import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../theme/app_colors.dart';

/// 极简设置页：只说明数据来源（AGENTS.md 第 40 节）。
class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key});

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
              _InfoTile(title: '后端地址', subtitle: kApiBaseUrl),
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
