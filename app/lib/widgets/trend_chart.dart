import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

/// 根据价格区间选择刻度小数位数（公开供测试）。
int trendDecimalsFor(List<double> points) {
  final minP = points.reduce((a, b) => a < b ? a : b);
  final maxP = points.reduce((a, b) => a > b ? a : b);
  final range = (maxP - minP).abs();
  if (range >= 1000) return 0;
  if (range >= 100) return 1;
  return 2;
}

String trendLabelFor(List<double> points, double v) =>
    v.toStringAsFixed(trendDecimalsFor(points));

/// 详情页走势图：折线 + 渐变填充 + 左侧价格刻度 + 可拖动十字虚线。
/// 拖动查看某天的价格：虚线顶端显示日期，选中点旁浮出价格气泡；松手即隐藏。
class TrendChart extends StatefulWidget {
  final List<double> points;
  final List<String> labels;
  final Color color;

  const TrendChart({
    super.key,
    required this.points,
    this.labels = const [],
    required this.color,
  });

  @override
  State<TrendChart> createState() => _TrendChartState();
}

class _TrendChartState extends State<TrendChart> {
  int? _selectedIndex;

  static const double _labelWidth = 52;

  void _select(Offset local, double width, int n) {
    final chartW = width - _labelWidth;
    if (chartW <= 0) return;
    final idx = (((local.dx - _labelWidth) / chartW) * (n - 1)).round().clamp(0, n - 1);
    if (idx != _selectedIndex) setState(() => _selectedIndex = idx);
  }

  void _hide() {
    if (_selectedIndex != null) setState(() => _selectedIndex = null);
  }

  @override
  Widget build(BuildContext context) {
    final points = widget.points;
    if (points.length < 2) return const SizedBox.shrink();
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapDown: (d) => _select(d.localPosition, width, points.length),
          onPanStart: (d) => _select(d.localPosition, width, points.length),
          onPanUpdate: (d) => _select(d.localPosition, width, points.length),
          // 松手即隐藏十字线
          onTapUp: (_) => _hide(),
          onTapCancel: _hide,
          onPanEnd: (_) => _hide(),
          onPanCancel: _hide,
          child: CustomPaint(
            painter: _TrendPainter(
              points: points,
              labels: widget.labels,
              color: widget.color,
              selectedIndex: _selectedIndex,
              labelWidth: _labelWidth,
            ),
            size: Size(width, 230),
          ),
        );
      },
    );
  }
}

class _TrendPainter extends CustomPainter {
  final List<double> points;
  final List<String> labels;
  final Color color;
  final int? selectedIndex;
  final double labelWidth;

  _TrendPainter({
    required this.points,
    required this.labels,
    required this.color,
    required this.selectedIndex,
    required this.labelWidth,
  });

  static const double _padV = 0.12;

  String _label(double v) => trendLabelFor(points, v);

  Offset _pos(int i, double chartLeft, double chartW, double top, double chartH) {
    final minP = points.reduce((a, b) => a < b ? a : b);
    final maxP = points.reduce((a, b) => a > b ? a : b);
    final range = (maxP - minP).abs();
    final y = range == 0
        ? top + chartH / 2
        : top + chartH - (points[i] - minP) / range * chartH;
    return Offset(chartLeft + i / (points.length - 1) * chartW, y);
  }

  @override
  void paint(Canvas canvas, Size size) {
    final chartLeft = labelWidth;
    final chartW = size.width - labelWidth;
    if (chartW <= 0) return;
    final top = size.height * _padV;
    final chartH = size.height - top * 2;

    final minP = points.reduce((a, b) => a < b ? a : b);
    final maxP = points.reduce((a, b) => a > b ? a : b);
    final range = (maxP - minP).abs();

    // ---- 左侧价格刻度 + 浅色横线 ----
    final labelStyle = const TextStyle(
      color: AppColors.textSecondary,
      fontSize: 10,
    );
    for (final t in <double>[0, 0.5, 1]) {
      final value = minP + range * t;
      final y = top + chartH - chartH * t;
      _drawDashedLine(canvas, Offset(chartLeft, y), Offset(size.width, y),
          AppColors.divider, 1, const [3, 4]);
      final tp = TextPainter(
        text: TextSpan(text: _label(value), style: labelStyle),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(chartLeft - tp.width - 5, y - tp.height / 2));
    }

    // ---- 折线与渐变填充 ----
    final line = Path()..moveTo(chartLeft, _pos(0, chartLeft, chartW, top, chartH).dy);
    for (var i = 1; i < points.length; i++) {
      final p = _pos(i, chartLeft, chartW, top, chartH);
      line.lineTo(p.dx, p.dy);
    }
    final fill = Path.from(line)
      ..lineTo(chartLeft + chartW, top + chartH)
      ..lineTo(chartLeft, top + chartH)
      ..close();
    final fillPaint = Paint()
      ..shader = ui.Gradient.linear(
        Offset(chartLeft, top),
        Offset(chartLeft, top + chartH),
        [color.withValues(alpha: 0.20), color.withValues(alpha: 0.0)],
      );
    canvas.drawPath(fill, fillPaint);

    final linePaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.2
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..isAntiAlias = true;
    canvas.drawPath(line, linePaint);

    // ---- 十字虚线（拖动中显示，松手即隐藏） ----
    final sel = selectedIndex;
    if (sel == null || sel < 0 || sel >= points.length) return;
    final p = _pos(sel, chartLeft, chartW, top, chartH);
    _drawDashedLine(canvas, Offset(p.dx, top), Offset(p.dx, top + chartH),
        AppColors.textSecondary, 1, const [5, 4]);
    _drawDashedLine(canvas, Offset(chartLeft, p.dy), Offset(size.width, p.dy),
        AppColors.textSecondary, 1, const [5, 4]);

    // 选中点：白边圆点
    canvas.drawCircle(p, 5.5, Paint()..color = AppColors.surface);
    canvas.drawCircle(p, 4, Paint()..color = color);

    // ---- 虚线顶端日期标签 ----
    final date = (sel < labels.length) ? labels[sel] : null;
    if (date != null && date.isNotEmpty) {
      _drawPill(canvas, date, p.dx, top + 4, AppColors.surfaceDark,
          minLeft: chartLeft + 2, maxRight: size.width - 2);
    }

    // ---- 价格气泡 ----
    _drawPill(canvas, _label(points[sel]), p.dx, p.dy - 34, AppColors.surfaceDark,
        minLeft: chartLeft + 2, maxRight: size.width - 2);
  }

  void _drawPill(Canvas canvas, String text, double cx, double cy, Color bg,
      {required double minLeft, required double maxRight}) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    const padH = 7.0, padV = 4.0;
    final w = tp.width + padH * 2;
    final h = tp.height + padV * 2;
    var x = cx - w / 2;
    x = x.clamp(minLeft, math.max(minLeft, maxRight - w));
    final rect = RRect.fromRectAndRadius(
      Rect.fromLTWH(x, cy, w, h),
      const Radius.circular(7),
    );
    canvas.drawRRect(rect, Paint()..color = bg.withValues(alpha: 0.95));
    tp.paint(canvas, Offset(x + padH, cy + padV));
  }

  void _drawDashedLine(Canvas canvas, Offset start, Offset end, Color color,
      double strokeWidth, List<double> dash) {
    final path = Path()..moveTo(start.dx, start.dy)..lineTo(end.dx, end.dy);
    final metrics = path.computeMetrics().toList();
    if (metrics.isEmpty) return;
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth;
    var on = true;
    var dist = 0.0;
    for (final metric in metrics) {
      final len = metric.length;
      while (dist < len) {
        final next = math.min(dist + dash[on ? 0 : 1], len);
        if (on) {
          canvas.drawPath(metric.extractPath(dist, next), paint);
        }
        dist = next;
        on = !on;
      }
    }
  }

  @override
  bool shouldRepaint(covariant _TrendPainter old) =>
      old.points != points ||
      old.color != color ||
      old.selectedIndex != selectedIndex;
}
