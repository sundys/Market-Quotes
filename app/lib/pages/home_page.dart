import 'dart:async';

import 'package:flutter/material.dart';

import '../core/format.dart';
import '../models/market_quote.dart';
import '../services/market_repository.dart';
import '../theme/app_colors.dart';
import '../widgets/gold_hero_card.dart';
import '../widgets/index_card.dart';
import '../widgets/sge_gold_card.dart';

/// 首页：打开即看，一眼知道涨跌（AGENTS.md 第 14/18/38 节）。
class HomePage extends StatefulWidget {
  final MarketRepository repository;
  final Duration refreshInterval;

  const HomePage({
    super.key,
    required this.repository,
    this.refreshInterval = const Duration(seconds: 60),
  });

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with WidgetsBindingObserver {
  MarketOverview? _overview;
  bool _loading = true;
  bool _networkError = false;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _init();
  }

  Future<void> _init() async {
    // 启动流程：先读本地缓存立即显示，再请求后端（AGENTS.md 第 18 节）
    final cached = await widget.repository.loadCached();
    if (!mounted) return;
    setState(() {
      if (cached != null) _overview = cached;
      _loading = _overview == null;
    });
    await _refresh();
    // refreshInterval 为 0 时不轮询（用于测试）
    if (widget.refreshInterval > Duration.zero) {
      _timer = Timer.periodic(widget.refreshInterval, (_) => _refresh());
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // 回到前台立即刷新一次
    if (state == AppLifecycleState.resumed) {
      _refresh();
    }
  }

  Future<void> _refresh() async {
    final overview = await widget.repository.fetchOverview();
    if (!mounted) return;
    setState(() {
      if (overview != null) {
        _overview = overview;
        _networkError = false;
      } else {
        _networkError = true;
      }
      _loading = false;
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  bool get _anyStale {
    final items = _overview?.items ?? const [];
    return items.any((e) => e.isStale);
  }

  String get _lastUpdated {
    final updatedAt = _overview?.updatedAt;
    if (updatedAt != null && updatedAt.isNotEmpty) return formatClock(updatedAt);
    final items = _overview?.items ?? const [];
    for (final item in items) {
      final t = formatClock(item.timestamp);
      if (t != '--:--') return t;
    }
    return '--:--';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
            children: [
              _buildHeader(context),
              const SizedBox(height: 20),
              if (_loading)
                const Padding(
                  padding: EdgeInsets.only(top: 120),
                  child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
                )
              else ...[
                GoldHeroCard(quote: _overview?.byId('gold_global')),
                _sectionTitle('主要指数'),
                _buildIndexRow(),
                _sectionTitle('中国黄金'),
                SgeGoldCard(quote: _overview?.byId('gold_cn')),
                const SizedBox(height: 20),
                _buildFooter(),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    final now = DateTime.now();
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '行情',
                style: TextStyle(
                  color: AppColors.textPrimary,
                  fontSize: 26,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                '${formatDate(now)} · 最新行情',
                style: const TextStyle(color: AppColors.textSecondary, fontSize: 13),
              ),
            ],
          ),
        ),
        IconButton(
          onPressed: () => Navigator.pushNamed(context, '/settings'),
          icon: const Icon(Icons.settings_outlined, color: AppColors.textSecondary),
          tooltip: '设置',
        ),
      ],
    );
  }

  Widget _sectionTitle(String title) {
    return Padding(
      padding: const EdgeInsets.only(top: 24, bottom: 10),
      child: Text(
        title,
        style: const TextStyle(
          color: AppColors.textPrimary,
          fontSize: 16,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }

  /// 屏幕较窄时指数卡片上下排列，禁止压缩价格（AGENTS.md 第 49 节）。
  Widget _buildIndexRow() {
    final ndx = _overview?.byId('nasdaq100');
    final sp = _overview?.byId('sp500');
    return LayoutBuilder(builder: (context, constraints) {
      final wide = constraints.maxWidth >= 360;
      final cards = [
        Expanded(child: IndexCard(quote: ndx)),
        const SizedBox(width: 12),
        Expanded(child: IndexCard(quote: sp, fallbackName: '标普500')),
      ];
      if (wide) return Row(children: cards);
      return Column(
        children: [
          IndexCard(quote: ndx),
          const SizedBox(height: 12),
          IndexCard(quote: sp, fallbackName: '标普500'),
        ],
      );
    });
  }

  Widget _buildFooter() {
    final staleTip = _anyStale || _networkError;
    return Column(
      children: [
        if (_networkError)
          const Padding(
            padding: EdgeInsets.only(bottom: 6),
            child: Text(
              '网络连接失败，正在自动重试',
              style: TextStyle(color: AppColors.warning, fontSize: 12),
            ),
          ),
        if (staleTip)
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Text(
              '部分数据可能延迟',
              style: TextStyle(
                color: AppColors.warning.withValues(alpha: 0.85),
                fontSize: 12,
              ),
            ),
          ),
        Text(
          '更新于 $_lastUpdated',
          style: const TextStyle(color: AppColors.textSecondary, fontSize: 11),
        ),
      ],
    );
  }
}
