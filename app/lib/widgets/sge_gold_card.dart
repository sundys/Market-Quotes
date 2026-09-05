import 'package:flutter/material.dart';

import '../core/format.dart';
import '../models/market_quote.dart';
import '../theme/app_colors.dart';
import 'change_label.dart';
import 'sparkline.dart';

/// 上海黄金 Au99.99 独立卡片，明确标注人民币/克（AGENTS.md 第 46/50 节）。
class SgeGoldCard extends StatelessWidget {
  final MarketQuote? quote;

  const SgeGoldCard({super.key, this.quote});

  @override
  Widget build(BuildContext context) {
    final q = quote;
    final accent = changeColor(q?.changePercent);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '上海黄金 Au99.99',
                      style: TextStyle(
                        color: AppColors.textPrimary,
                        fontSize: 17,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    SizedBox(height: 2),
                    Text(
                      '上海黄金交易所 · 人民币 / 克',
                      style: TextStyle(color: AppColors.textSecondary, fontSize: 12),
                    ),
                  ],
                ),
              ),
              _StatusDot(status: q?.marketStatus),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: AnimatedValueText(
                  value: formatPrice(q?.price, q?.currency ?? 'CNY'),
                  style: const TextStyle(
                    color: AppColors.textPrimary,
                    fontSize: 30,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              SizedBox(width: 110, height: 36, child: _sparkline(accent)),
            ],
          ),
          const SizedBox(height: 10),
          ChangeRow(change: q?.change, changePercent: q?.changePercent),
        ],
      ),
    );
  }

  Widget _sparkline(Color accent) {
    final points = quote?.sparkline ?? const <double>[];
    if (points.length < 2) return const SizedBox.shrink();
    return Sparkline(points: points, color: accent);
  }
}

class _StatusDot extends StatelessWidget {
  final String? status;

  const _StatusDot({this.status});

  @override
  Widget build(BuildContext context) {
    final open = status == 'open';
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: open ? AppColors.positive : AppColors.neutral,
          ),
        ),
        const SizedBox(width: 6),
        Text(
          open ? '交易中' : '已收盘',
          style: const TextStyle(color: AppColors.textSecondary, fontSize: 11),
        ),
      ],
    );
  }
}
