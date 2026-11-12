import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 状态 / 筛选 chip。默认是灰字白底细边；选中态传 ink 底白字。
class StatusChip extends StatelessWidget {
  const StatusChip({
    super.key,
    required this.label,
    this.color = PulseColors.sub,
    this.background = PulseColors.card,
    this.borderColor = PulseColors.line,
    this.dot = false,
    this.dotColor,
    this.icon,
    this.padding = const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
    this.textStyle,
    this.onTap,
  });

  final String label;
  final Color color;
  final Color background;
  final Color borderColor;
  final bool dot;
  final Color? dotColor;
  final IconData? icon;
  final EdgeInsetsGeometry padding;
  final TextStyle? textStyle;
  final VoidCallback? onTap;

  /// 筛选行选中态：墨黑底 + 白字。
  factory StatusChip.selected({
    Key? key,
    required String label,
    VoidCallback? onTap,
  }) {
    return StatusChip(
      key: key,
      label: label,
      color: Colors.white,
      background: PulseColors.ink,
      borderColor: PulseColors.ink,
      textStyle: const TextStyle(
        fontSize: 10.5,
        height: 1.2,
        letterSpacing: 0.2,
        fontWeight: FontWeight.w600,
        color: Colors.white,
      ),
      onTap: onTap,
    );
  }

  /// 图例里的小圆点 chip（如「● 运行 5」）。
  factory StatusChip.legend({
    Key? key,
    required String label,
    required Color color,
  }) {
    return StatusChip(
      key: key,
      label: label,
      color: PulseColors.sub,
      dot: true,
      dotColor: color,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      background: Colors.transparent,
      borderColor: Colors.transparent,
    );
  }

  @override
  Widget build(BuildContext context) {
    final Widget row = Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (dot) ...<Widget>[
          Container(
            width: 5,
            height: 5,
            decoration: BoxDecoration(
              color: dotColor ?? color,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 5),
        ],
        if (icon != null) ...<Widget>[
          Icon(icon, size: 12, color: dotColor ?? color),
          const SizedBox(width: 4),
        ],
        Text(label, style: textStyle ?? PulseText.chip.copyWith(color: color)),
      ],
    );

    final Widget chip = Container(
      padding: padding,
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(PulseRadius.chip),
        border: Border.all(color: borderColor, width: 1),
      ),
      child: row,
    );

    if (onTap == null) {
      return chip;
    }
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: chip,
    );
  }
}
