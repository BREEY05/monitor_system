import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 车间地图卡（设备页）：网格底 + 三个分区块 + 设备点 + 数字孪生入口。
class WorkshopMap extends StatelessWidget {
  const WorkshopMap({super.key, this.showCaption = true});

  final bool showCaption;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: <Widget>[
        const Positioned.fill(
            child: CustomPaint(painter: _WorkshopMapPainter())),
        Positioned(
          top: 10,
          right: 10,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.92),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: PulseColors.accentLine),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const Icon(
                  Icons.view_in_ar_rounded,
                  size: 11,
                  color: PulseColors.accent,
                ),
                const SizedBox(width: 4),
                Text(
                  '数字孪生',
                  style: PulseText.meta.copyWith(
                    fontSize: 9,
                    fontWeight: FontWeight.w600,
                    color: PulseColors.accentInk,
                  ),
                ),
              ],
            ),
          ),
        ),
        if (showCaption)
          Positioned(
            left: 12,
            bottom: 9,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: <Widget>[
                Text(
                  '一号车间',
                  style: PulseText.cardTitle.copyWith(fontSize: 11.5),
                ),
                const SizedBox(width: 5),
                Text(
                  '· 7 台设备',
                  style: PulseText.meta.copyWith(fontSize: 9.5),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _WorkshopMapPainter extends CustomPainter {
  const _WorkshopMapPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final Paint gridPaint = Paint()
      ..color = PulseColors.line2
      ..strokeWidth = 1;
    const double step = 26;
    for (double x = step; x < size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), gridPaint);
    }
    for (double y = step; y < size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }

    void zone(Rect rect, Color color) {
      final RRect rrect =
          RRect.fromRectAndRadius(rect, const Radius.circular(9));
      canvas.drawRRect(rrect, Paint()..color = color.withValues(alpha: 0.10));
      canvas.drawRRect(
        rrect,
        Paint()
          ..color = color.withValues(alpha: 0.26)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1,
      );
    }

    zone(
      Rect.fromLTWH(size.width * 0.06, size.height * 0.16, size.width * 0.28,
          size.height * 0.38),
      PulseColors.accent,
    );
    zone(
      Rect.fromLTWH(size.width * 0.40, size.height * 0.21, size.width * 0.21,
          size.height * 0.50),
      PulseColors.green,
    );
    zone(
      Rect.fromLTWH(size.width * 0.66, size.height * 0.13, size.width * 0.27,
          size.height * 0.31),
      PulseColors.amber,
    );

    void spot(double dx, double dy, Color color, {bool ring = false}) {
      final Offset center = Offset(size.width * dx, size.height * dy);
      if (ring) {
        canvas.drawCircle(
            center, 11, Paint()..color = color.withValues(alpha: 0.14));
      }
      canvas.drawCircle(
          center, 6.5, Paint()..color = color.withValues(alpha: 0.18));
      canvas.drawCircle(center, 3.4, Paint()..color = color);
    }

    spot(0.20, 0.36, PulseColors.accent, ring: true);
    spot(0.50, 0.47, PulseColors.green);
    spot(0.78, 0.28, PulseColors.amber);
    spot(0.89, 0.62, PulseColors.purple);
  }

  @override
  bool shouldRepaint(covariant _WorkshopMapPainter oldDelegate) => false;
}
