import 'package:flutter/material.dart';

import '../core/format.dart';
import '../models/market_quote.dart';
import '../theme/app_colors.dart';
import 'change_label.dart';
import 'sparkline.dart';

/// 并排小指数卡片：NASDAQ 100 / S&P 500（AGENTS.md 第 46/49 节）。
class IndexCard extends StatelessWidget {
  final MarketQuote? quote;
  final String fallbackName;

  const IndexCard({super.key, this.quote, this.fallbackName = '纳斯达克100'});

  @override
  Widget build(BuildContext context) {
    final q = quote;
    final accent = changeColor(q?.changePercent);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            q?.name ?? fallbackName,
            style: const TextStyle(
              color: AppColors.textSecondary,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 10),
          AnimatedValueText(
            value: formatPrice(q?.price, q?.currency ?? 'USD'),
            style: const TextStyle(
              color: AppColors.textPrimary,
              fontSize: 22,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 10),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: ChangeRow(
                  change: q?.change,
                  changePercent: q?.changePercent,
                  percentFontSize: 14,
                  changeFontSize: 12,
                ),
              ),
              SizedBox(width: 56, height: 24, child: _sparkline(accent)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _sparkline(Color accent) {
    final points = quote?.sparkline ?? const <double>[];
    if (points.length < 2) return const SizedBox.shrink();
    return Sparkline(points: points, color: accent, strokeWidth: 1.8);
  }
}
