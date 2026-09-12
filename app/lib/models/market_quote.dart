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
  // 盘面明细（指数详情页展示；无数据的源为 null）
  final double? open;
  final double? high;
  final double? low;
  final double? prevClose;
  final double? volume;

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
    this.open,
    this.high,
    this.low,
    this.prevClose,
    this.volume,
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
      open: (json['open'] as num?)?.toDouble(),
      high: (json['high'] as num?)?.toDouble(),
      low: (json['low'] as num?)?.toDouble(),
      prevClose: (json['prev_close'] as num?)?.toDouble(),
      volume: (json['volume'] as num?)?.toDouble(),
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

/// GET /api/market/{id}/history 的响应模型：收盘价序列 + 对应日期标签。
class MarketHistory {
  final String id;
  final String period;
  final List<double> points;
  final List<String> labels;
  final bool isStale;

  const MarketHistory({
    required this.id,
    required this.period,
    required this.points,
    required this.labels,
    required this.isStale,
  });

  factory MarketHistory.fromJson(Map<String, dynamic> json) {
    return MarketHistory(
      id: json['id'] as String? ?? '',
      period: json['period'] as String? ?? '',
      points: ((json['points'] as List?) ?? const [])
          .map((e) => (e as num).toDouble())
          .toList(),
      labels: ((json['labels'] as List?) ?? const [])
          .map((e) => e as String)
          .toList(),
      isStale: json['is_stale'] as bool? ?? false,
    );
  }
}
