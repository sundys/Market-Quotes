/// 行情文本格式化工具（AGENTS.md 第 11/47 节）。
library;

import 'package:intl/intl.dart';

final NumberFormat _priceFmt = NumberFormat('#,##0.00');
final NumberFormat _changeFmt = NumberFormat('+0.00;-0.00');
final NumberFormat _pctFmt = NumberFormat('+0.00%;-0.00%');

String formatPrice(double? price, String currency) {
  if (price == null) return '--';
  final prefix = currency == 'USD' ? '\$' : (currency == 'CNY' ? '¥' : '');
  return '$prefix${_priceFmt.format(price)}';
}

String formatChange(double? change) => change == null ? '--' : _changeFmt.format(change);

String formatPercent(double? percent) => percent == null ? '--' : _pctFmt.format(percent / 100.0);

String formatClock(String? isoTimestamp) {
  if (isoTimestamp == null || isoTimestamp.isEmpty) return '--:--';
  // Dart 解析带时区偏移的字符串时会规范化为 UTC（isUtc=true），
  // 必须转回设备本地时间，否则中国用户看到的是 UTC 时刻。
  final dt = DateTime.tryParse(isoTimestamp)?.toLocal();
  if (dt == null) return '--:--';
  return DateFormat('HH:mm').format(dt);
}

const List<String> _weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

String formatDate(DateTime dt) =>
    '${dt.year}年${dt.month}月${dt.day}日 ${_weekdays[dt.weekday - 1]}';
