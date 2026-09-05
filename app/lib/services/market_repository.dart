import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/market_quote.dart';
import 'api_client.dart';

/// 行情仓库：远端获取 + 三级本地缓存（AGENTS.md 第 18/19 节）。
/// 打开 App 先读本地缓存立即显示，再请求后端更新。
class MarketRepository {
  static const String _cacheKey = 'market_overview_cache_v1';

  final ApiClient apiClient;
  final SharedPreferences prefs;

  MarketRepository({required this.apiClient, required this.prefs});

  Future<MarketOverview?> fetchOverview() async {
    try {
      final overview = await apiClient.fetchOverview();
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

  Future<void> _saveLocal(MarketOverview overview) async {
    await prefs.setString(_cacheKey, jsonEncode(overview.toJson()));
  }
}
