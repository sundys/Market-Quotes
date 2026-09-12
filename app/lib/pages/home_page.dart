import 'dart:async';

import 'package:flutter/material.dart';

import '../core/format.dart';
import '../models/market_quote.dart';
import '../services/market_repository.dart';
import '../services/settings_service.dart';
import '../theme/app_colors.dart';
import '../widgets/gold_hero_card.dart';
import '../widgets/index_card.dart';
import 'detail_page.dart';

/// 首页：打开即看，一眼知道涨跌（AGENTS.md 第 14/18/38 节）。
class HomePage extends StatefulWidget {
  final MarketRepository repository;
  final SettingsService settings;
  final Duration refreshInterval;

  const HomePage({
    super.key,
    required this.repository,
    required this.settings,
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
  final PageController _heroController = PageController();
  int _heroPage = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // 用户在设置页修改后端地址后立即重新拉取
    widget.settings.apiBaseUrl.addListener(_onBaseUrlChanged);
    _init();
  }

  void _onBaseUrlChanged() {
    if (!mounted) return;
    setState(() {}); // 立即反映“已配置/未配置”状态
    _refresh();
  }

  /// 无实时数据时用静态元数据构造占位行情，保证卡片始终可进详情页。
  static const Map<String, List<String>> _quoteMeta = {
    'gold_cn': ['上海黄金 Au99.99', 'Au99.99', 'CNY'],
    'gold_global': ['国际黄金期货', 'GC', 'USD'],
    'nasdaq100': ['纳斯达克100', '100.NDX', 'USD'],
    'sp500': ['标普500', '100.SPX', 'USD'],
    'dowjones': ['道琼斯', '100.DJIA', 'USD'],
  };

  void _openDetail(String quoteId) {
    final meta = _quoteMeta[quoteId];
    if (meta == null) return;
    MarketQuote? quote = _overview?.byId(quoteId);
    quote ??= MarketQuote(
      id: quoteId,
      name: meta[0],
      symbol: meta[1],
      currency: meta[2],
      source: '',
      marketStatus: 'unknown',
      isStale: false,
    );
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => DetailPage(quote: quote!, repository: widget.repository),
      ),
    );
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
    _heroController.dispose();
    widget.settings.apiBaseUrl.removeListener(_onBaseUrlChanged);
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
              if (!widget.settings.isConfigured)
                _buildNotConfigured(context)
              else if (_loading)
                const Padding(
                  padding: EdgeInsets.only(top: 120),
                  child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
                )
              else ...[
                // 黄金双卡：默认中国黄金，左滑切换国际黄金；点击进详情
                SizedBox(
                  height: 216,
                  child: PageView(
                    controller: _heroController,
                    onPageChanged: (page) => setState(() => _heroPage = page),
                    children: [
                      GestureDetector(
                        onTap: () => _openDetail('gold_cn'),
                        child: GoldHeroCard(quote: _overview?.byId('gold_cn')),
                      ),
                      GestureDetector(
                        onTap: () => _openDetail('gold_global'),
                        child: GoldHeroCard(quote: _overview?.byId('gold_global')),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: List.generate(2, (i) {
                    final active = i == _heroPage;
                    return Container(
                      width: active ? 16 : 6,
                      height: 6,
                      margin: const EdgeInsets.symmetric(horizontal: 3),
                      decoration: BoxDecoration(
                        color: active ? AppColors.primary : AppColors.divider,
                        borderRadius: BorderRadius.circular(3),
                      ),
                    );
                  }),
                ),
                _sectionTitle('主要指数'),
                _buildIndexRow(),
                const SizedBox(height: 20),
                _buildFooter(),
              ],
            ],
          ),
        ),
      ),
    );
  }

  /// 未配置后端地址时的引导（地址只在设置页录入，不写死在代码里）。
  Widget _buildNotConfigured(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        children: [
          const Icon(Icons.dns_outlined, size: 48, color: AppColors.textSecondary),
          const SizedBox(height: 16),
          const Text(
            '尚未配置后端地址',
            style: TextStyle(
              color: AppColors.textPrimary,
              fontSize: 17,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            '请先在设置中填写你自己部署的\n行情后端服务地址',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textSecondary, fontSize: 13.5, height: 1.5),
          ),
          const SizedBox(height: 20),
          FilledButton.icon(
            onPressed: () => Navigator.pushNamed(context, '/settings'),
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.primary,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            ),
            icon: const Icon(Icons.settings_outlined, size: 18),
            label: const Text('去设置'),
          ),
        ],
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

  /// 指数：三张全宽卡片（新格式含盘面明细），点击进详情。
  Widget _buildIndexRow() {
    return Column(
      children: [
        for (final entry in {
          'nasdaq100': '纳斯达克100',
          'sp500': '标普500',
          'dowjones': '道琼斯',
        }.entries) ...[
          GestureDetector(
            onTap: () => _openDetail(entry.key),
            child: IndexCard(
              quote: _overview?.byId(entry.key),
              fallbackName: entry.value,
            ),
          ),
          if (entry.key != 'dowjones') const SizedBox(height: 12),
        ],
      ],
    );
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
