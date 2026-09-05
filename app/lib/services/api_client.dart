import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/market_quote.dart';

/// 后端 API 基地址。
/// 默认为真机调试使用的局域网地址；可用编译参数覆盖：
///   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
const String kApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://200.200.200.29:8000',
);

class ApiException implements Exception {
  final String message;
  ApiException(this.message);

  @override
  String toString() => message;
}

class ApiClient {
  final http.Client _client;

  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  /// 获取首页全部行情。超时/网络错误/非 200 抛 ApiException。
  Future<MarketOverview> fetchOverview({Duration timeout = const Duration(seconds: 15)}) async {
    try {
      final response = await _client
          .get(Uri.parse('$kApiBaseUrl/api/market/overview'))
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
