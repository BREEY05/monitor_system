import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 设置列表的一行：图标 + 标题 + 右侧值 + 箭头。
class ListTileRow extends StatelessWidget {
  const ListTileRow({
    super.key,
    required this.icon,
    required this.title,
    this.value,
    this.onTap,
    this.showDivider = false,
  });

  final IconData icon;
  final String title;
  final String? value;
  final VoidCallback? onTap;
  final bool showDivider;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        height: 46,
        decoration: BoxDecoration(
          border: showDivider
              ? const Border(bottom: BorderSide(color: PulseColors.line2))
              : null,
        ),
        child: Row(
          children: <Widget>[
            Container(
              width: 28,
              height: 28,
              decoration: BoxDecoration(
                color: PulseColors.card2,
                borderRadius: BorderRadius.circular(9),
              ),
              child: Icon(icon, size: 15, color: PulseColors.icon),
            ),
            const SizedBox(width: 11),
            Expanded(child: Text(title, style: PulseText.listTitle)),
            if (value != null) Text(value!, style: PulseText.listValue),
            const SizedBox(width: 4),
            const Icon(
              Icons.chevron_right_rounded,
              size: 15,
              color: PulseColors.chevron,
            ),
          ],
        ),
      ),
    );
  }
}
