import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 顶栏小方按钮：36×36 白底圆角 12，可带红点。
class PulseIconButton extends StatelessWidget {
  const PulseIconButton({
    super.key,
    required this.icon,
    this.onTap,
    this.size = 36,
    this.iconSize = 17,
    this.showDot = false,
    this.filled = false,
    this.tooltip,
  });

  final IconData icon;
  final VoidCallback? onTap;
  final double size;
  final double iconSize;
  final bool showDot;
  final bool filled;
  final String? tooltip;

  @override
  Widget build(BuildContext context) {
    final Widget button = GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: filled ? PulseColors.ink : PulseColors.card,
          borderRadius: BorderRadius.circular(PulseRadius.iconButton),
          border: Border.all(
            color: filled ? PulseColors.ink : PulseColors.line,
            width: 1,
          ),
          boxShadow: filled ? PulseShadow.card : PulseShadow.iconButton,
        ),
        child: Stack(
          alignment: Alignment.center,
          children: <Widget>[
            Icon(
              icon,
              size: iconSize,
              color: filled ? Colors.white : PulseColors.icon,
            ),
            if (showDot)
              Positioned(
                right: size / 2 - 7,
                top: size / 2 - 8,
                child: Container(
                  width: 6,
                  height: 6,
                  decoration: BoxDecoration(
                    color: PulseColors.red,
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 1.2),
                  ),
                ),
              ),
          ],
        ),
      ),
    );

    if (tooltip == null) {
      return button;
    }
    return Tooltip(message: tooltip!, child: button);
  }
}
