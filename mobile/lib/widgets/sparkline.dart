import 'dart:math' as math;

import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 自绘折线 / 面积图。数值会被自动缩放，另可选虚线阈值。
class Sparkline extends StatelessWidget {
  const Sparkline({
    super.key,
    required this.values,
    required this.color,
    this.width,
    this.height = 32,
    this.lineWidth = 1.6,
    this.area = true,
    this.showEndDot = false,
    this.threshold,
    this.thresholdFraction,
    this.thresholdColor = PulseColors.amber,
    this.gradient,
  });

  /// 原始值序列（不需要归一化）。
  final List<double> values;
  final Color color;
  final double? width;
  final double height;
  final double lineWidth;
  final bool area;
  final bool showEndDot;

  /// 阈值线（与 values 同一量纲），会参与缩放以便虚线可见。
  final double? threshold;

  /// 仅用于展示的阈值线位置（0 = 顶部，1 = 底部）。
  /// 当阈值远大于实际读数、但设计稿希望虚线靠近折线时使用。
  final double? thresholdFraction;
  final Color thresholdColor;
  final Gradient? gradient;

  @override
  Widget build(BuildContext context) {
    final Widget painter = CustomPaint(
      size: Size(width ?? double.infinity, height),
      painter: _SparklinePainter(
        values: values,
        color: color,
        lineWidth: lineWidth,
        area: area,
        showEndDot: showEndDot,
        threshold: threshold,
        thresholdFraction: thresholdFraction,
        thresholdColor: thresholdColor,
        gradient: gradient ?? PulseTheme.sparkArea(color),
      ),
    );
    if (width == null) {
      return SizedBox(height: height, width: double.infinity, child: painter);
    }
    return painter;
  }
}

class _SparklinePainter extends CustomPainter {
  const _SparklinePainter({
    required this.values,
    required this.color,
    required this.lineWidth,
    required this.area,
    required this.showEndDot,
    required this.threshold,
    required this.thresholdFraction,
    required this.thresholdColor,
    required this.gradient,
  });

  final List<double> values;
  final Color color;
  final double lineWidth;
  final bool area;
  final bool showEndDot;
  final double? threshold;
  final double? thresholdFraction;
  final Color thresholdColor;
  final Gradient gradient;

  /// 轻量三次平滑：避免随机样本呈锯齿状，贴近设计稿中的柔和趋势线。
  static List<double> _smooth(List<double> input) {
    if (input.length < 5) {
      return input;
    }
    List<double> current = List<double>.from(input);
    for (int pass = 0; pass < 2; pass++) {
      final List<double> next = List<double>.from(current);
      for (int i = 1; i < current.length - 1; i++) {
        next[i] = (current[i - 1] + 2 * current[i] + current[i + 1]) / 4;
      }
      current = next;
    }
    return current;
  }

  @override
  void paint(Canvas canvas, Size size) {
    if (values.length < 2 || size.width <= 0 || size.height <= 0) {
      return;
    }
    final List<double> data = _smooth(values);

    final double topPad = showEndDot ? 3 : 2;
    final double bottomPad = showEndDot ? 3 : 2;
    final double usableHeight = math.max(1, size.height - topPad - bottomPad);

    double minValue = data.reduce(math.min);
    double maxValue = data.reduce(math.max);
    if (threshold != null) {
      minValue = math.min(minValue, threshold!);
      maxValue = math.max(maxValue, threshold!);
    }
    final double span = math.max(0.0001, maxValue - minValue);
    final double stepX = size.width / (data.length - 1);

    Offset pointAt(int index) {
      final double ratio = (data[index] - minValue) / span;
      return Offset(
        index * stepX,
        topPad + (1 - ratio) * usableHeight,
      );
    }

    final List<Offset> points = <Offset>[
      for (int i = 0; i < data.length; i++) pointAt(i),
    ];

    // 阈值虚线（在折线下方先画）。
    if (threshold != null || thresholdFraction != null) {
      final double ratio = thresholdFraction != null
          ? 1 - thresholdFraction!
          : (threshold! - minValue) / span;
      final double y = topPad + (1 - ratio) * usableHeight;
      final Paint dashPaint = Paint()
        ..color = thresholdColor.withValues(alpha: 0.55)
        ..strokeWidth = 1
        ..style = PaintingStyle.stroke;
      const double dashWidth = 3.2;
      const double dashGap = 3.2;
      double x = 0;
      while (x < size.width) {
        canvas.drawLine(
          Offset(x, y),
          Offset(math.min(x + dashWidth, size.width), y),
          dashPaint,
        );
        x += dashWidth + dashGap;
      }
    }

    final Path linePath = Path()..moveTo(points.first.dx, points.first.dy);
    for (int i = 1; i < points.length; i++) {
      final Offset prev = points[i - 1];
      final Offset cur = points[i];
      final double midX = (prev.dx + cur.dx) / 2;
      linePath.cubicTo(midX, prev.dy, midX, cur.dy, cur.dx, cur.dy);
    }

    if (area) {
      final Path areaPath = Path.from(linePath)
        ..lineTo(size.width, size.height)
        ..lineTo(0, size.height)
        ..close();
      final Paint areaPaint = Paint()
        ..shader = gradient.createShader(
          Rect.fromLTWH(0, 0, size.width, size.height),
        );
      canvas.drawPath(areaPath, areaPaint);
    }

    final Paint linePaint = Paint()
      ..color = color
      ..strokeWidth = lineWidth
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..style = PaintingStyle.stroke;
    canvas.drawPath(linePath, linePaint);

    if (showEndDot) {
      final Offset last = points.last;
      canvas.drawCircle(last, 3.4, Paint()..color = Colors.white);
      canvas.drawCircle(
        last,
        2.6,
        Paint()
          ..color = color
          ..style = PaintingStyle.fill,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _SparklinePainter oldDelegate) {
    return oldDelegate.values != values ||
        oldDelegate.color != color ||
        oldDelegate.threshold != threshold ||
        oldDelegate.thresholdFraction != thresholdFraction ||
        oldDelegate.lineWidth != lineWidth ||
        oldDelegate.showEndDot != showEndDot;
  }
}
