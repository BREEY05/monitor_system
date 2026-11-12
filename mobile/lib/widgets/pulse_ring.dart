import 'dart:math' as math;

import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 渐变健康环：92% + 「系统健康分」+「较昨日 +3」。
/// 参考稿里只有总览页做 2.4s 低幅度呼吸，这里做 1.5% 缩放。
class PulseRing extends StatefulWidget {
  const PulseRing({
    super.key,
    required this.progress,
    required this.score,
    this.caption = '系统健康分',
    this.delta,
    this.size = 148,
    this.strokeWidth = 9,
    this.breathing = true,
  });

  final double progress;
  final String score;
  final String caption;
  final String? delta;
  final double size;
  final double strokeWidth;
  final bool breathing;

  @override
  State<PulseRing> createState() => _PulseRingState();
}

class _PulseRingState extends State<PulseRing>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _scale;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2400),
    );
    _scale = Tween<double>(begin: 1.0, end: 1.015).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
    if (widget.breathing) {
      _controller.repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final Widget ring = SizedBox(
      width: widget.size,
      height: widget.size,
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          TweenAnimationBuilder<double>(
            tween: Tween<double>(begin: 0, end: widget.progress),
            duration: const Duration(milliseconds: 1100),
            curve: Curves.easeOutCubic,
            builder: (BuildContext context, double value, Widget? child) {
              return CustomPaint(
                size: Size.square(widget.size),
                painter: _RingPainter(
                  progress: value,
                  strokeWidth: widget.strokeWidth,
                ),
              );
            },
          ),
          Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Row(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.baseline,
                textBaseline: TextBaseline.alphabetic,
                children: <Widget>[
                  Text(widget.score, style: PulseText.score),
                  const Text('%', style: PulseText.scoreUnit),
                ],
              ),
              const SizedBox(height: 3),
              Text(
                widget.caption,
                style: PulseText.label.copyWith(color: PulseColors.sub),
              ),
              if (widget.delta != null) ...<Widget>[
                const SizedBox(height: 3),
                Text(
                  widget.delta!,
                  style: PulseText.meta.copyWith(
                    color: PulseColors.greenInk,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );

    if (!widget.breathing) {
      return ring;
    }
    return ScaleTransition(scale: _scale, child: ring);
  }
}

class _RingPainter extends CustomPainter {
  const _RingPainter({required this.progress, required this.strokeWidth});

  final double progress;
  final double strokeWidth;

  @override
  void paint(Canvas canvas, Size size) {
    final Rect rect = Offset.zero & size;
    final double radius = (math.min(size.width, size.height) - strokeWidth) / 2;
    final Rect arcRect = Rect.fromCircle(
      center: rect.center,
      radius: radius,
    );

    final Paint track = Paint()
      ..color = const Color(0xFFEAEDF2)
      ..strokeWidth = strokeWidth
      ..style = PaintingStyle.stroke;
    canvas.drawArc(arcRect, 0, math.pi * 2, false, track);

    final double sweep = (math.pi * 2) * progress.clamp(0.0, 1.0);
    if (sweep <= 0) {
      return;
    }
    final Paint arc = Paint()
      ..strokeWidth = strokeWidth
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..shader = const SweepGradient(
        colors: <Color>[
          PulseColors.accent,
          PulseColors.accent2,
          PulseColors.accent
        ],
        stops: <double>[0, 0.7, 1],
        transform: GradientRotation(-math.pi / 2),
      ).createShader(arcRect);
    canvas.drawArc(arcRect, -math.pi / 2, sweep, false, arc);
  }

  @override
  bool shouldRepaint(covariant _RingPainter oldDelegate) {
    return oldDelegate.progress != progress ||
        oldDelegate.strokeWidth != strokeWidth;
  }
}
