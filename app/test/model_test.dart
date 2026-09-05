import 'package:flutter_test/flutter_test.dart';
import 'package:market_quotes/models/market_quote.dart';

void main() {
  group('MarketQuote.fromJson', () {
    test('parses full quote', () {
      final q = MarketQuote.fromJson({
        'id': 'gold_global',
        'name': '国际黄金',
        'symbol': 'XAUUSD=X',
        'price': 3521.80,
        'change': 18.60,
        'change_percent': 0.53,
        'currency': 'USD',
        'unit': 'oz',
        'source': 'yfinance',
        'timestamp': '2026-09-05T12:29:50+08:00',
        'market_status': 'open',
        'is_stale': false,
        'sparkline': [3510.0, 3521.8],
      });
      expect(q.price, 3521.80);
      expect(q.changePercent, 0.53);
      expect(q.isStale, isFalse);
      expect(q.sparkline.length, 2);
    });

    test('tolerates null price and missing fields', () {
      final q = MarketQuote.fromJson({'id': 'sp500'});
      expect(q.price, isNull);
      expect(q.isStale, isFalse);
      expect(q.sparkline, isEmpty);
    });
  });

  group('MarketOverview', () {
    final overview = MarketOverview.fromJson({
      'updated_at': '2026-09-05T12:30:00+08:00',
      'items': [
        {'id': 'gold_global', 'price': 1.0},
        {'id': 'gold_cn', 'price': 2.0},
      ],
      'server_time': '2026-09-05T12:30:00+08:00',
    });

    test('byId finds item', () {
      expect(overview.byId('gold_cn')!.price, 2.0);
    });

    test('byId returns null for missing', () {
      expect(overview.byId('nasdaq100'), isNull);
    });

    test('round-trips through json', () {
      final restored = MarketOverview.fromJson(overview.toJson());
      expect(restored.items.length, 2);
      expect(restored.updatedAt, overview.updatedAt);
    });
  });
}
