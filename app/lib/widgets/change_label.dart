import 'package:flutter/material.dart';

import '../core/format.dart';
import '../theme/app_colors.dart';

/// 涨跌颜色语义（AGENTS.md 第 16 节）。
Color changeColor(double? changePercent) {
  if (changePercent == null || changePercent == 0) return AppColors.neutral;
  return changePercent > 0 ? AppColors.positive : AppColors.negative;
}

/// 价格数字变化时的克制动画：150~250ms 轻微淡入（AGENTS.md 第 17/56 节）。
class AnimatedValueText extends StatelessWidget {
  final String value;
  final TextStyle style;
  final Duration duration;

  const AnimatedValueText({
    super.key,
    required this.value,
    required this.style,
    this.duration = const Duration(milliseconds: 200),
  });

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0.0, end: 1.0),
      duration: duration,
      builder: (context, opacity, _) {
        return Opacity(
          opacity: opacity == 1.0 ? 1.0 : 0.35 + 0.65 * opacity,
          child: Text(value, style: style, maxLines: 1, overflow: TextOverflow.ellipsis),
        );
      },
      // 仅当数值变化时重建动画
      key: ValueKey(value),
    );
  }
}

/// 涨跌幅 + 涨跌额行。涨跌幅比涨跌额更醒目（AGENTS.md 第 15/47 节）。
class ChangeRow extends StatelessWidget {
  final double? change;
  final double? changePercent;
  final Color? color;
  final Color percentBackground;
  final double percentFontSize;
  final double changeFontSize;

  const ChangeRow({
    super.key,
    required this.change,
    required this.changePercent,
    this.color,
    this.percentBackground = Colors.transparent,
    this.percentFontSize = 16,
    this.changeFontSize = 13,
  });

  @override
  Widget build(BuildContext context) {
    final c = color ?? changeColor(changePercent);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.baseline,
      textBaseline: TextBaseline.alphabetic,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(
            color: percentBackground,
            borderRadius: BorderRadius.circular(8),
          ),
          child: AnimatedValueText(
            value: formatPercent(changePercent),
            style: TextStyle(
              color: c,
              fontSize: percentFontSize,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        const SizedBox(width: 10),
        AnimatedValueText(
          value: formatChange(change),
          style: TextStyle(
            color: c,
            fontSize: changeFontSize,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}
