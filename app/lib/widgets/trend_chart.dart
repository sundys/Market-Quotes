import 'package:flutter/material.dart';

/// 详情页走势图：折线 + 底部渐变填充，无坐标轴/网格（AGENTS.md 第 55 节）。
class TrendChart extends StatelessWidget {
  final List<double> points;
  final Color color;

  const TrendChart({super.key, required this.points, required this.color});

  @override
  Widget build(BuildContext context) {
    if (points.length < 2) {
      return const SizedBox.shrink();
    }
    return CustomPaint(
      painter: _TrendPainter(points: points, color: color),
      size: const Size(double.infinity, 220),
    );
  }
}

class _TrendPainter extends CustomPainter {
  final List<double> points;
  final Color color;

  _TrendPainter({required this.points, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final minP = points.reduce((a, b) => a < b ? a : b);
    final maxP = points.reduce((a, b) => a > b ? a : b);
    final range = (maxP - minP).abs();
    // 上下各留 8% 余量，避免线贴边
    final pad = size.height * 0.08;
    final chartH = size.height - pad * 2;
    final dx = size.width / (points.length - 1);

    Offset pos(int i) => Offset(
          i * dx,
          range == 0 ? size.height / 2 : pad + chartH - (points[i] - minP) / range * chartH,
        );

    final line = Path()..moveTo(pos(0).dx, pos(0).dy);
    for (var i = 1; i < points.length; i++) {
      line.lineTo(pos(i).dx, pos(i).dy);
    }

    // 底部渐变填充
    final fill = Path.from(line)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    final fillPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [color.withValues(alpha: 0.22), color.withValues(alpha: 0.0)],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));
    canvas.drawPath(fill, fillPaint);

    final linePaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.2
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..isAntiAlias = true;
    canvas.drawPath(line, linePaint);

    // 末端圆点
    canvas.drawCircle(pos(points.length - 1), 3.5, Paint()..color = color);
  }

  @override
  bool shouldRepaint(covariant _TrendPainter old) =>
      old.points != points || old.color != color;
}
