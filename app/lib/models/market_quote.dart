/// 统一行情模型，字段与后端 MarketQuote（AGENTS.md 第 8/25 节）一一对应。
class MarketQuote {
  final String id;
  final String name;
  final String symbol;
  final double? price;
  final double? change;
  final double? changePercent;
  final String currency;
  final String? unit;
  final String source;
  final String? timestamp;
  final String marketStatus;
  final bool isStale;
  final List<double> sparkline;

  const MarketQuote({
    required this.id,
    required this.name,
    required this.symbol,
    this.price,
    this.change,
    this.changePercent,
    required this.currency,
    this.unit,
    required this.source,
    this.timestamp,
    required this.marketStatus,
    required this.isStale,
    this.sparkline = const [],
  });

  factory MarketQuote.fromJson(Map<String, dynamic> json) {
    return MarketQuote(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      symbol: json['symbol'] as String? ?? '',
      price: (json['price'] as num?)?.toDouble(),
      change: (json['change'] as num?)?.toDouble(),
      changePercent: (json['change_percent'] as num?)?.toDouble(),
      currency: json['currency'] as String? ?? '',
      unit: json['unit'] as String?,
      source: json['source'] as String? ?? '',
      timestamp: json['timestamp'] as String?,
      marketStatus: json['market_status'] as String? ?? 'unknown',
      isStale: json['is_stale'] as bool? ?? false,
      sparkline: ((json['sparkline'] as List?) ?? const [])
          .map((e) => (e as num).toDouble())
          .toList(),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'symbol': symbol,
        'price': price,
        'change': change,
        'change_percent': changePercent,
        'currency': currency,
        'unit': unit,
        'source': source,
        'timestamp': timestamp,
        'market_status': marketStatus,
        'is_stale': isStale,
        'sparkline': sparkline,
      };
}

/// GET /api/market/overview 的响应模型。
class MarketOverview {
  final String? updatedAt;
  final List<MarketQuote> items;
  final String? serverTime;

  const MarketOverview({
    required this.updatedAt,
    required this.items,
    this.serverTime,
  });

  factory MarketOverview.fromJson(Map<String, dynamic> json) {
    return MarketOverview(
      updatedAt: json['updated_at'] as String?,
      items: ((json['items'] as List?) ?? const [])
          .map((e) => MarketQuote.fromJson(e as Map<String, dynamic>))
          .toList(),
      serverTime: json['server_time'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'updated_at': updatedAt,
        'items': items.map((e) => e.toJson()).toList(),
        'server_time': serverTime,
      };

  MarketQuote? byId(String id) {
    for (final item in items) {
      if (item.id == id) return item;
    }
    return null;
  }
}
