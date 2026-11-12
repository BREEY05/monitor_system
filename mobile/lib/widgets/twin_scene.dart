import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/models/device.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 数字孪生占位场景：类等距地面网格 + 分区色块 + 设备体块 + 热点标签。
/// M1 用 CustomPainter 模拟；M2 计划用 WebView 承载 Three.js 真实模型。
class TwinScene extends StatelessWidget {
  const TwinScene({
    super.key,
    required this.spots,
    required this.selectedId,
    required this.onSpotTap,
    this.showLabels = true,
  });

  final List<TwinSpot> spots;
  final String selectedId;
  final ValueChanged<TwinSpot> onSpotTap;
  final bool showLabels;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final double width = constraints.maxWidth;
        final double height = constraints.maxHeight;
        return Stack(
          clipBehavior: Clip.none,
          children: <Widget>[
            Positioned.fill(
              child: CustomPaint(
                painter:
                    _TwinScenePainter(spots: spots, selectedId: selectedId),
              ),
            ),
            if (showLabels)
              for (final TwinSpot spot in spots)
                Positioned(
                  left: spot.dx * width,
                  top: spot.dy * height,
                  child: FractionalTranslation(
                    translation: const Offset(-0.5, -1),
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => onSpotTap(spot),
                      child: _SpotLabel(
                        spot: spot,
                        selected: spot.id == selectedId,
                      ),
                    ),
                  ),
                ),
          ],
        );
      },
    );
  }
}

class _SpotLabel extends StatelessWidget {
  const _SpotLabel({required this.spot, required this.selected});

  final TwinSpot spot;
  final bool selected;

  Color get _dotColor {
    switch (spot.state) {
      case TwinState.running:
        return PulseColors.green;
      case TwinState.watch:
        return PulseColors.amber;
      case TwinState.maintenance:
        return PulseColors.amber;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 26,
      padding: const EdgeInsets.symmetric(horizontal: 9),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.96),
        borderRadius: BorderRadius.circular(13),
        border: Border.all(
          color: selected ? PulseColors.accent : const Color(0x14101828),
          width: 1,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: selected ? const Color(0x333D5AFE) : const Color(0x1A101828),
            blurRadius: selected ? 12 : 8,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(color: _dotColor, shape: BoxShape.circle),
          ),
          const SizedBox(width: 5),
          Text(
            spot.name,
            style: PulseText.cardTitle.copyWith(
              fontSize: 10.5,
              color: PulseColors.ink,
            ),
          ),
          if (spot.note != null) ...<Widget>[
            const SizedBox(width: 4),
            Text(
              spot.note!,
              style: TextStyle(
                fontSize: 8.5,
                height: 1.1,
                fontWeight: FontWeight.w600,
                color: selected ? PulseColors.accentInk : PulseColors.amberInk,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _TwinScenePainter extends CustomPainter {
  const _TwinScenePainter({required this.spots, required this.selectedId});

  final List<TwinSpot> spots;
  final String selectedId;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width <= 0 || size.height <= 0) {
      return;
    }

    // 地面：柔和椭圆 + 网格（一次剪裁）。
    final Rect floor = Rect.fromCenter(
      center: Offset(size.width * 0.5, size.height * 0.64),
      width: size.width * 1.25,
      height: size.height * 0.82,
    );
    final Paint floorPaint = Paint()
      ..shader = RadialGradient(
        colors: <Color>[
          Colors.white.withValues(alpha: 0.95),
          const Color(0xFFE7ECF5).withValues(alpha: 0.55),
          Colors.white.withValues(alpha: 0.0),
        ],
        stops: const <double>[0, 0.72, 1],
      ).createShader(floor);
    canvas.drawOval(floor, floorPaint);

    canvas.save();
    canvas.clipPath(Path()..addOval(floor));
    final Paint gridPaint = Paint()
      ..color = const Color(0x0F101828)
      ..strokeWidth = 1;
    const double step = 26;
    for (double x = floor.left; x < floor.right; x += step) {
      canvas.drawLine(Offset(x, floor.top), Offset(x, floor.bottom), gridPaint);
    }
    for (double y = floor.top; y < floor.bottom; y += step) {
      canvas.drawLine(Offset(floor.left, y), Offset(floor.right, y), gridPaint);
    }
    canvas.restore();

    // 分区色块：底部左右两块淡色区域。
    void zonePatch(Offset center, double radiusX, double radiusY, Color color) {
      final Rect rect = Rect.fromCenter(
        center: center,
        width: radiusX,
        height: radiusY,
      );
      final Paint paint = Paint()
        ..shader = RadialGradient(
          colors: <Color>[
            color.withValues(alpha: 0.16),
            color.withValues(alpha: 0.0)
          ],
        ).createShader(rect);
      canvas.drawOval(rect, paint);
    }

    zonePatch(
      Offset(size.width * 0.30, size.height * 0.74),
      size.width * 0.52,
      size.height * 0.32,
      PulseColors.accent,
    );
    zonePatch(
      Offset(size.width * 0.60, size.height * 0.46),
      size.width * 0.46,
      size.height * 0.28,
      PulseColors.green,
    );
    zonePatch(
      Offset(size.width * 0.84, size.height * 0.58),
      size.width * 0.36,
      size.height * 0.26,
      PulseColors.amber,
    );

    // 设备体块：按热点锚点绘制，标签浮在体块上方。
    for (final TwinSpot spot in spots) {
      final bool selected = spot.id == selectedId;
      final Offset anchor = Offset(
        spot.dx * size.width,
        spot.dy * size.height + 34,
      );
      _drawDevice(canvas, anchor, spot, selected);
    }
  }

  void _drawDevice(Canvas canvas, Offset center, TwinSpot spot, bool selected) {
    final Color accent;
    switch (spot.state) {
      case TwinState.running:
        accent = PulseColors.accent;
        break;
      case TwinState.watch:
        accent = PulseColors.amber;
        break;
      case TwinState.maintenance:
        accent = PulseColors.amber;
        break;
    }

    // 地面投影
    canvas.drawOval(
      Rect.fromCenter(
        center: center + const Offset(0, 12),
        width: selected ? 58 : 46,
        height: 14,
      ),
      Paint()..color = const Color(0x12101828),
    );

    // 选中光环
    if (selected) {
      canvas.drawCircle(
        center + const Offset(0, 2),
        34,
        Paint()
          ..shader = RadialGradient(
            colors: <Color>[
              PulseColors.accent.withValues(alpha: 0.20),
              PulseColors.accent.withValues(alpha: 0.02),
            ],
          ).createShader(Rect.fromCircle(center: center, radius: 34)),
      );
      canvas.drawCircle(
        center + const Offset(0, 2),
        31,
        Paint()
          ..color = PulseColors.accent.withValues(alpha: 0.45)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.2,
      );
    }

    final Rect body = Rect.fromCenter(
      center: center + const Offset(0, 2),
      width: selected ? 46 : 38,
      height: selected ? 26 : 22,
    );
    final RRect bodyRRect =
        RRect.fromRectAndRadius(body, const Radius.circular(5));
    canvas.drawRRect(
      bodyRRect,
      Paint()..color = const Color(0xFFFDFEFF),
    );
    canvas.drawRRect(
      bodyRRect,
      Paint()
        ..color = const Color(0xFFD4DAE6)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1,
    );

    // 顶面（等距菱形）
    final double halfW = body.width / 2;
    final Path top = Path()
      ..moveTo(center.dx - halfW, body.top)
      ..lineTo(center.dx, body.top - (selected ? 12 : 9))
      ..lineTo(center.dx + halfW, body.top)
      ..lineTo(center.dx, body.top + (selected ? 8 : 6))
      ..close();
    canvas.drawPath(top, Paint()..color = const Color(0xFFF2F5FB));
    canvas.drawPath(
      top,
      Paint()
        ..color = const Color(0xFFD4DAE6)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1,
    );

    // 状态色条 + 面板细节
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(body.left + 5, body.top + 7, 12, 3),
        const Radius.circular(2),
      ),
      Paint()..color = accent.withValues(alpha: 0.85),
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(body.left + 5, body.top + 13, 20, 2.4),
        const Radius.circular(1.5),
      ),
      Paint()..color = const Color(0xFFDDE3EC),
    );
    canvas.drawCircle(
      Offset(body.right - 8, body.top + 9),
      2.2,
      Paint()..color = accent,
    );
  }

  @override
  bool shouldRepaint(covariant _TwinScenePainter oldDelegate) {
    return oldDelegate.selectedId != selectedId || oldDelegate.spots != spots;
  }
}
