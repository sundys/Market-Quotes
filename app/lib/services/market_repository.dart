import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/market_quote.dart';
import 'api_client.dart';
import 'settings_service.dart';
/// 行情仓库：远端获取 + 三级本地缓存（AGENTS.md 第 18/19 节）。
/// 打开 App 先读本地缓存立即显示，再请求后端更新。
/// 后端地址来自 SettingsService（用户在设置页录入）。
class MarketRepository {
  static const String _cacheKey = 'market_overview_cache_v1';

  final ApiClient apiClient;
  final SharedPreferences prefs;
  final SettingsService settings;

  MarketRepository({
    required this.apiClient,
    required this.prefs,
    required this.settings,
  });

  /// 返回 null 表示失败（未配置地址/网络错误/服务器异常），调用方保留缓存展示。
  Future<MarketOverview?> fetchOverview() async {
    final baseUrl = settings.apiBaseUrl.value;
    if (baseUrl.isEmpty) return null;
    try {
      final overview = await apiClient.fetchOverview(baseUrl: baseUrl);
      await _saveLocal(overview);
      return overview;
    } on ApiException {
      return null;
    }
  }

  Future<MarketOverview?> loadCached() async {
    final raw = prefs.getString(_cacheKey);
    if (raw == null) return null;
    try {
      return MarketOverview.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  /// 历史走势：失败返回 null（详情页显示空态）。
  Future<MarketHistory?> fetchHistory(String quoteId, String period) async {
    final baseUrl = settings.apiBaseUrl.value;
    if (baseUrl.isEmpty) return null;
    try {
      return await apiClient.fetchHistory(baseUrl: baseUrl, quoteId: quoteId, period: period);
    } on ApiException {
      return null;
    }
  }

  Future<void> _saveLocal(MarketOverview overview) async {
    await prefs.setString(_cacheKey, jsonEncode(overview.toJson()));
  }
}
