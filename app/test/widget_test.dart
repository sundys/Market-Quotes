import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:market_quotes/models/market_quote.dart';
import 'package:market_quotes/services/api_client.dart';
import 'package:market_quotes/services/market_repository.dart';
import 'package:market_quotes/services/settings_service.dart';
import 'package:market_quotes/theme/app_colors.dart';
import 'package:market_quotes/widgets/gold_hero_card.dart';
import 'package:market_quotes/widgets/index_card.dart';
import 'package:market_quotes/widgets/trend_chart.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String fakeOverviewJson = '''
{
  "updated_at": "2026-09-05T12:30:00+08:00",
  "items": [
    {"id": "gold_global", "name": "国际黄金", "symbol": "XAUUSD=X", "price": 3521.80,
     "change": 18.60, "change_percent": 0.53, "currency": "USD", "unit": "oz",
     "source": "yfinance", "timestamp": "2026-09-05T12:29:50+08:00",
     "market_status": "open", "is_stale": false, "sparkline": [3510, 3516, 3521.8]},
    {"id": "nasdaq100", "name": "纳斯达克100", "symbol": "^NDX", "price": 23456.78,
     "change": 125.30, "change_percent": 0.54, "currency": "USD",
     "source": "yfinance", "timestamp": "2026-09-05T12:29:50+08:00",
     "market_status": "open", "is_stale": false},
    {"id": "gold_cn", "name": "上海黄金 Au99.99", "symbol": "Au99.99", "price": 958.0,
     "change": -7.95, "change_percent": -0.82, "currency": "CNY", "unit": "g",
     "source": "AKShare/SGE", "timestamp": "2026-09-05T12:28:55+08:00",
     "market_status": "closed", "is_stale": false, "sparkline": [960, 958]}
  ]
}
''';

Future<MarketRepository> makeRepository({String? responseBody}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final settings = SettingsService(prefs);
  await settings.setApiBaseUrl('http://test.example:8000');
  final api = ApiClient(
    client: MockClient((request) async {
      // 后端地址必须来自设置，而不是硬编码常量
      expect(request.url.host, 'test.example');
      return http.Response(
        responseBody ?? fakeOverviewJson,
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    }),
  );
  return MarketRepository(apiClient: api, prefs: prefs, settings: settings);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('settings normalizes backend url', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final settings = SettingsService(prefs);
    await settings.setApiBaseUrl(' 192.168.1.5:8000/ ');
    expect(settings.apiBaseUrl.value, 'http://192.168.1.5:8000');
    expect(settings.isConfigured, isTrue);
    await settings.setApiBaseUrl('   ');
    expect(settings.isConfigured, isFalse);
  });

  test('repository skips fetch when backend not configured', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final settings = SettingsService(prefs);
    var called = false;
    final repo = MarketRepository(
      apiClient: ApiClient(
        client: MockClient((request) async {
          called = true;
          return http.Response('{}', 200);
        }),
      ),
      prefs: prefs,
      settings: settings,
    );
    expect(await repo.fetchOverview(), isNull);
    expect(called, isFalse);
  });

  test('repository fetches and caches overview', () async {
    final repo = await makeRepository();
    final overview = await repo.fetchOverview();
    expect(overview, isNotNull);
    expect(overview!.byId('gold_global')!.price, 3521.80);

    // 第二次应能从本地缓存读出（即使后端不可达）
    final prefs2 = await SharedPreferences.getInstance();
    final settings2 = SettingsService(prefs2);
    final offlineRepo = MarketRepository(
      apiClient: ApiClient(
        client: MockClient((request) async => http.Response('', 500)),
      ),
      prefs: prefs2,
      settings: settings2,
    );
    final cached = await offlineRepo.loadCached();
    expect(cached, isNotNull);
    expect(cached!.byId('gold_cn')!.price, 958.0);
  });

  test('repository returns null on server error', () async {
    final repo = await makeRepository(responseBody: 'oops');
    final overview = await repo.fetchOverview();
    expect(overview, isNull);
  });

  testWidgets('hero card shows price and change', (tester) async {
    final overview =
        MarketOverview.fromJson(jsonDecode(fakeOverviewJson) as Map<String, dynamic>);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: GoldHeroCard(quote: overview.byId('gold_global'))),
      ),
    );
    expect(find.text('国际黄金'), findsOneWidget);
    expect(find.text('\$3,521.80'), findsOneWidget);
    expect(find.text('+0.53%'), findsOneWidget);
  });

  testWidgets('hero card renders SGE gold in dark style with yuan price', (tester) async {
    final overview =
        MarketOverview.fromJson(jsonDecode(fakeOverviewJson) as Map<String, dynamic>);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: GoldHeroCard(quote: overview.byId('gold_cn'))),
      ),
    );
    expect(find.text('上海黄金 Au99.99'), findsOneWidget);
    expect(find.text('上海黄金交易所 · ¥ / 克'), findsOneWidget);
    expect(find.text('¥958.00'), findsOneWidget);
  });

  testWidgets('trend chart builds and tap interaction works', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: TrendChart(points: [100.0, 105.0, 103.0, 110.0], color: AppColors.positive),
          ),
        ),
      ),
    );
    // 点击/拖动选择十字线位置，不应抛异常
    await tester.tap(find.byType(TrendChart));
    await tester.pump();
    final gesture = await tester.startGesture(tester.getCenter(find.byType(TrendChart)));
    await gesture.moveBy(const Offset(60, 0));
    await gesture.up();
    await tester.pumpAndSettle();
  });

  test('trend label formatting by range', () {
    expect(trendLabelFor([100.0, 110.0], 110.0), '110.00'); // 小区间 2 位小数
    expect(trendLabelFor([0.0, 150.0], 75.0), '75.0'); // 中区间 1 位小数
    expect(trendLabelFor([20000.0, 27000.0], 26506.99), '26507'); // 大区间整数
  });

  testWidgets('index card falls back to placeholder without data', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: IndexCard(quote: null))),
    );
    expect(find.text('--'), findsWidgets);
  });

  test('change colors follow reference scheme', () {
    expect(AppColors.positive, const Color(0xFF16B364));
    expect(AppColors.negative, const Color(0xFFE5484D));
  });
}
