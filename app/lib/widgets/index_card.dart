import 'package:flutter/material.dart';

import '../core/format.dart';
import '../models/market_quote.dart';
import '../theme/app_colors.dart';
import 'change_label.dart';

/// 首页指数卡片（全宽三行格式）：
/// 名称 + 价格 / 今开·昨收·涨跌幅 / 最高·最低·成交量。
class IndexCard extends StatelessWidget {
  final MarketQuote? quote;
  final String fallbackName;

  const IndexCard({super.key, this.quote, this.fallbackName = '纳斯达克100'});

  @override
  Widget build(BuildContext context) {
    final q = quote;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              // 与下方两列统计相同的两等分网格：价格起点与"昨收/最低"列对齐
              Expanded(
                child: Text(
                  q?.name ?? fallbackName,
                  style: const TextStyle(
                    color: AppColors.textPrimary,
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Expanded(
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.centerLeft,
                  child: AnimatedValueText(
                    value: formatPrice(q?.price, q?.currency ?? 'USD'),
                    style: const TextStyle(
                      color: AppColors.textPrimary,
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _statRow(
            '今开', formatPrice(q?.open, q?.currency ?? 'USD'),
            '昨收', formatPrice(q?.prevClose, q?.currency ?? 'USD'),
          ),
          const SizedBox(height: 8),
          _statRow(
            '最高', formatPrice(q?.high, q?.currency ?? 'USD'),
            '最低', formatPrice(q?.low, q?.currency ?? 'USD'),
          ),
          const SizedBox(height: 8),
          _statRow(
            q != null && (q.changePercent ?? 0) < 0 ? '跌幅' : '涨跌幅',
            formatPercent(q?.changePercent),
            '成交量', formatVolume(q?.volume),
            valueColor1: changeColor(q?.changePercent),
          ),
        ],
      ),
    );
  }

  /// 两列数据行：标签与数值基线对齐，列宽各半。
  Widget _statRow(String label1, String value1, String label2, String value2,
      {Color? valueColor1, Color? valueColor2}) {
    Widget cell(String label, String value, {Color? color}) {
      return Expanded(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            Text(
              '$label：',
              style: const TextStyle(
                color: AppColors.textSecondary,
                fontSize: 11.5,
              ),
            ),
            const SizedBox(width: 2),
            Flexible(
              child: Text(
                value,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: color ?? AppColors.textPrimary,
                  fontSize: 12.5,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
      );
    }

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        cell(label1, value1, color: valueColor1),
        cell(label2, value2, color: valueColor2),
      ],
    );
  }
}
