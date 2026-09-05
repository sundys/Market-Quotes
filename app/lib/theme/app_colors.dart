/// 语义颜色集中定义（AGENTS.md 第 16/51 节）。
/// 按 AGENTS.md 第 45/51 节：以参考图 ss.jpg 为最终视觉基准，
/// 上涨=绿色、下跌=红色；如需切换为国内红涨绿跌，只需调整这里。
library;

import 'package:flutter/material.dart';

abstract class AppColors {
  // 品牌蓝：选中态/强调
  static const Color primary = Color(0xFF3D6BF5);

  // 背景：极浅冷灰
  static const Color background = Color(0xFFF3F5F9);

  // 卡片
  static const Color surface = Colors.white;
  static const Color surfaceDark = Color(0xFF191E2A);

  // 涨跌（参考图体系）
  static const Color positive = Color(0xFF16B364);
  static const Color negative = Color(0xFFE5484D);
  static const Color neutral = Color(0xFF8A94A6);

  // 文本
  static const Color textPrimary = Color(0xFF171C26);
  static const Color textPrimaryInverse = Colors.white;
  static const Color textSecondary = Color(0xFF8A94A6);
  static const Color textSecondaryInverse = Color(0xFFA8B0C0);

  // 分隔/边框
  static const Color divider = Color(0xFFE8EBF1);

  // 提示（stale 数据）
  static const Color warning = Color(0xFFB7791F);
}
