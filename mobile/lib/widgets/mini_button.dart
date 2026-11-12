import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 卡片底部的小操作按钮：墨黑主按钮 / 白底描边次级按钮。
/// 可点击热区最小 32 高。
class MiniButton extends StatelessWidget {
  const MiniButton({
    super.key,
    required this.label,
    this.onPressed,
    this.primary = false,
    this.icon,
    this.height = 30,
    this.expand = false,
    this.fontSize = 10,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool primary;
  final IconData? icon;
  final double height;
  final bool expand;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final Widget child = Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        if (icon != null) ...<Widget>[
          Icon(
            icon,
            size: fontSize + 3,
            color: primary ? Colors.white : PulseColors.ink,
          ),
          const SizedBox(width: 5),
        ],
        Text(
          label,
          style: PulseText.button.copyWith(
            fontSize: fontSize,
            color: primary ? Colors.white : PulseColors.ink,
          ),
        ),
      ],
    );

    // 注意：不能用 Container(alignment: ...) —— 在 Wrap / 宽松约束下它会撑满整行，
    // 导致「追问 AI / 查看设备 / 忽略」三个小按钮各自占满一行。这里显式区分是否撑满。
    final Widget button = Material(
      color: primary ? PulseColors.ink : PulseColors.card,
      borderRadius: BorderRadius.circular(PulseRadius.chip),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onPressed,
        child: Container(
          height: height,
          width: expand ? double.infinity : null,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(PulseRadius.chip),
            border: Border.all(
              color: primary ? PulseColors.ink : PulseColors.line,
              width: 1,
            ),
          ),
          child: Center(widthFactor: 1, heightFactor: 1, child: child),
        ),
      ),
    );

    return button;
  }
}
