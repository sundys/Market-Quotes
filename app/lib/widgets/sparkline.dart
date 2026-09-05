import 'package:flutter/material.dart';

/// 极简迷你走势图（AGENTS.md 第 55 节）：
/// 只显示趋势，无坐标轴/网格/刻度。
class Sparkline extends StatelessWidget {
  final List<double> points;
  final Color color;
  final double strokeWidth;

  const Sparkline({
    super.key,
    required this.points,
    required this.color,
    this.strokeWidth = 2.0,
  });

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _SparklinePainter(points: points, color: color, strokeWidth: strokeWidth),
      size: const Size(double.infinity, 40),
    );
  }
}

class _SparklinePainter extends CustomPainter {
  final List<double> points;
  final Color color;
  final double strokeWidth;

  _SparklinePainter({
    required this.points,
    required this.color,
    required this.strokeWidth,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (points.length < 2) return;
    final minP = points.reduce((a, b) => a < b ? a : b);
    final maxP = points.reduce((a, b) => a > b ? a : b);
    final range = (maxP - minP).abs();
    final dx = size.width / (points.length - 1);

    final path = Path();
    for (var i = 0; i < points.length; i++) {
      final y = range == 0
          ? size.height / 2
          : size.height - (points[i] - minP) / range * size.height;
      if (i == 0) {
        path.moveTo(0, y);
      } else {
        path.lineTo(i * dx, y);
      }
    }

    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..isAntiAlias = true;
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _SparklinePainter old) =>
      old.points != points || old.color != color;
}
