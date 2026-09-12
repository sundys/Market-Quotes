import 'package:flutter/material.dart';

import '../core/format.dart';
import '../models/market_quote.dart';
import '../services/market_repository.dart';
import '../theme/app_colors.dart';
import '../widgets/change_label.dart';
import '../widgets/trend_chart.dart';

/// 行情详情页：价格头 + 走势图 + 天/周/月/半年/年 切换（AGENTS.md 第 29 节）。
class DetailPage extends StatefulWidget {
  final MarketQuote quote;
  final MarketRepository repository;

  const DetailPage({super.key, required this.quote, required this.repository});

  @override
  State<DetailPage> createState() => _DetailPageState();
}

class _DetailPageState extends State<DetailPage> {
  static const List<(String, String)> _periods = [
    ('1d', '天'),
    ('1w', '周'),
    ('1m', '月'),
    ('6m', '半年'),
    ('1y', '年'),
  ];

  late String _period;
  MarketHistory? _history;
  bool _loading = true;
  bool _loadFailed = false;

  @override
  void initState() {
    super.initState();
    _period = '1m';
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final history = await widget.repository.fetchHistory(widget.quote.id, _period);
    if (!mounted) return;
    setState(() {
      _history = history;
      _loading = false;
      _loadFailed = history == null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final q = widget.quote;
    final accent = changeColor(q.changePercent);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(
          q.name,
          style: const TextStyle(
              color: AppColors.textPrimary, fontWeight: FontWeight.w700, fontSize: 18),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(24),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _subtitle(q),
                  style: const TextStyle(color: AppColors.textSecondary, fontSize: 12.5),
                ),
                const SizedBox(height: 10),
                AnimatedValueText(
                  value: formatPrice(q.price, q.currency),
                  style: const TextStyle(
                    color: AppColors.textPrimary,
                    fontSize: 32,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 10),
                ChangeRow(change: q.change, changePercent: q.changePercent),
              ],
            ),
          ),
          if (_isIndex(q) && q.open != null) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(24),
              ),
              child: Column(
                children: [
                  _statRow('今开', formatPrice(q.open, q.currency),
                      '昨收', formatPrice(q.prevClose, q.currency)),
                  const SizedBox(height: 10),
                  _statRow('最高', formatPrice(q.high, q.currency),
                      '最低', formatPrice(q.low, q.currency)),
                  const SizedBox(height: 10),
                  _statRow(
                    q.changePercent != null && q.changePercent! < 0 ? '跌幅' : '涨幅',
                    formatPercent(q.changePercent),
                    '成交量',
                    formatVolume(q.volume),
                    valueColor: changeColor(q.changePercent),
                  ),
                ],
              ),
            ),
          ],
          if (_isGold(q)) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(24),
              ),
              child: Column(
                children: [
                  _statRow('今开', formatPrice(q.open, q.currency),
                      '最高', formatPrice(q.high, q.currency)),
                  const SizedBox(height: 10),
                  _statRow(_prevLabel(q), formatPrice(q.prevClose, q.currency),
                      '最低', formatPrice(q.low, q.currency)),
                  const SizedBox(height: 10),
                  _statRow('涨跌幅', formatPercent(q.changePercent),
                      '涨跌额', formatChange(q.change),
                      valueColor: changeColor(q.changePercent)),
                ],
              ),
            ),
          ],
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.fromLTRB(8, 20, 8, 8),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(24),
            ),
            child: _loading
                ? const SizedBox(
                    height: 220,
                    child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
                  )
                : (_history == null || _history!.points.length < 2)
                    ? SizedBox(
                        height: 220,
                        child: Center(
                          child: Text(
                            _loadFailed ? '走势数据加载失败' : '暂无走势数据',
                            style: const TextStyle(
                                color: AppColors.textSecondary, fontSize: 13.5),
                          ),
                        ),
                      )
                    : Column(
                        children: [
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 12),
                            child: TrendChart(
                              points: _history!.points,
                              labels: _history!.labels,
                              color: accent,
                            ),
                          ),
                          if (_history!.isStale)
                            const Padding(
                              padding: EdgeInsets.only(top: 4),
                              child: Text(
                                '数据可能延迟',
                                style: TextStyle(color: AppColors.warning, fontSize: 11),
                              ),
                            ),
                        ],
                      ),
          ),
          const SizedBox(height: 16),
          Row(
            children: _periods
                .map((p) => Expanded(child: _periodChip(p.$1, p.$2)))
                .toList(),
          ),
          const SizedBox(height: 16),
          Center(
            child: Text(
              '走势仅供趋势参考，不构成投资建议',
              style: const TextStyle(color: AppColors.textSecondary, fontSize: 11),
            ),
          ),
        ],
      ),
    );
  }

  bool _isIndex(MarketQuote q) => q.symbol.startsWith('100.');

  bool _isGold(MarketQuote q) => q.symbol == 'GC' || q.symbol == 'Au99.99';

  String _prevLabel(MarketQuote q) => q.symbol == 'GC' ? '昨结' : '昨收';

  Widget _statRow(String label1, String value1, String label2, String value2,
      {Color? valueColor}) {
    final valueStyle = TextStyle(
      color: valueColor ?? AppColors.textPrimary,
      fontSize: 14,
      fontWeight: FontWeight.w600,
    );
    return Row(
      children: [
        Expanded(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text('$label1：',
                  style: const TextStyle(
                      color: AppColors.textSecondary, fontSize: 13)),
              const SizedBox(width: 2),
              Text(value1, style: valueStyle),
            ],
          ),
        ),
        Expanded(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text('$label2：',
                  style: const TextStyle(
                      color: AppColors.textSecondary, fontSize: 13)),
              const SizedBox(width: 2),
              Text(value2, style: valueStyle),
            ],
          ),
        ),
      ],
    );
  }

  Widget _periodChip(String value, String label) {
    final selected = value == _period;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: GestureDetector(
        onTap: () {
          if (!selected) {
            _period = value;
            _load();
          }
        },
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 9),
          decoration: BoxDecoration(
            color: selected ? AppColors.primary : AppColors.surface,
            borderRadius: BorderRadius.circular(14),
          ),
          child: Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: selected ? Colors.white : AppColors.textSecondary,
            ),
          ),
        ),
      ),
    );
  }

  String _subtitle(MarketQuote q) {
    switch (q.symbol) {
      case 'GC':
        return '国际黄金期货 · COMEX · \$ / 盎司';
      case 'Au99.99':
        return '上海黄金交易所 · ¥ / 克';
      case '100.NDX':
        return '纳斯达克100指数';
      case '100.SPX':
        return '标普500指数';
      case '100.DJIA':
        return '道琼斯工业指数';
      default:
        return '国际黄金 · XAU/USD · \$ / 盎司';
    }
  }
}
