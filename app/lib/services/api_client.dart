import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/market_quote.dart';

class ApiException implements Exception {
  final String message;
  ApiException(this.message);

  @override
  String toString() => message;
}

class ApiClient {
  final http.Client _client;

  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  /// 获取首页全部行情。后端地址由设置页配置（不写死在代码中）。
  /// 超时/网络错误/非 200 抛 ApiException。
  Future<MarketOverview> fetchOverview({
    required String baseUrl,
    Duration timeout = const Duration(seconds: 15),
  }) async {
    if (baseUrl.trim().isEmpty) {
      throw ApiException('未配置后端地址');
    }
    try {
      final response = await _client
          .get(Uri.parse('$baseUrl/api/market/overview'))
          .timeout(timeout);
      if (response.statusCode != 200) {
        throw ApiException('服务器异常 (${response.statusCode})');
      }
      final body = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
      return MarketOverview.fromJson(body);
    } on TimeoutException {
      throw ApiException('连接超时');
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException('网络连接失败');
    }
  }

  void dispose() => _client.close();
}
