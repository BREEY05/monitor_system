import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 小节标题：左侧标题 + 右侧「全部 12 条 ›」。
class SectionHeader extends StatelessWidget {
  const SectionHeader({
    super.key,
    required this.title,
    this.trailing,
    this.onTrailingTap,
    this.padding = const EdgeInsets.fromLTRB(2, 0, 2, 9),
  });

  final String title;
  final String? trailing;
  final VoidCallback? onTrailingTap;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: padding,
      child: Row(
        children: <Widget>[
          Expanded(child: Text(title, style: PulseText.sectionTitle)),
          if (trailing != null)
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onTrailingTap,
              child: Row(
                children: <Widget>[
                  Text(trailing!, style: PulseText.sectionLink),
                  const SizedBox(width: 2),
                  const Icon(
                    Icons.chevron_right_rounded,
                    size: 14,
                    color: PulseColors.chevron,
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
