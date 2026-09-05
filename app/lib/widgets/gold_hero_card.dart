import 'package:flutter/material.dart';

import '../core/format.dart';
import '../models/market_quote.dart';
import '../theme/app_colors.dart';
import 'change_label.dart';
import 'sparkline.dart';

/// 核心黄金主卡片：深色背景（AGENTS.md 第 46/48 节）。
class GoldHeroCard extends StatelessWidget {
  final MarketQuote? quote;

  const GoldHeroCard({super.key, this.quote});

  @override
  Widget build(BuildContext context) {
    final q = quote;
    final up = (q?.changePercent ?? 0) >= 0;
    final accent = q == null || (q.changePercent == null)
        ? AppColors.neutral
        : (up ? AppColors.positive : AppColors.negative);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.surfaceDark,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      q?.name ?? '国际黄金',
                      style: const TextStyle(
                        color: AppColors.textPrimaryInverse,
                        fontSize: 17,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      // 现货与期货分别标注，防止把期货价格当成现货（AGENTS.md 第 4.1 节）
                      (q?.symbol == 'GC=F') ? 'COMEX 期金 · \$ / 盎司' : 'XAU/USD · \$ / 盎司',
                      style: const TextStyle(
                        color: AppColors.textSecondaryInverse,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              _MarketStatusChip(status: q?.marketStatus),
            ],
          ),
          const SizedBox(height: 16),
          AnimatedValueText(
            value: formatPrice(q?.price, q?.currency ?? 'USD'),
            style: const TextStyle(
              color: AppColors.textPrimaryInverse,
              fontSize: 34,
              fontWeight: FontWeight.w700,
              letterSpacing: -0.5,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: ChangeRow(
                  change: q?.change,
                  changePercent: q?.changePercent,
                  percentBackground: accent.withValues(alpha: 0.16),
                ),
              ),
              const SizedBox(width: 12),
              SizedBox(width: 110, height: 40, child: _sparkline(accent)),
            ],
          ),
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

class _MarketStatusChip extends StatelessWidget {
  final String? status;

  const _MarketStatusChip({this.status});

  @override
  Widget build(BuildContext context) {
    final open = status == 'open';
    final unknown = status == null || status == 'unknown';
    if (unknown) return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: open ? Colors.white.withValues(alpha: 0.10) : Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
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
            style: const TextStyle(color: AppColors.textSecondaryInverse, fontSize: 11),
          ),
        ],
      ),
    );
  }
}
