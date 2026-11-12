import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';
import 'package:pulse_mobile/widgets/highlight_text.dart';
import 'package:pulse_mobile/widgets/mini_button.dart';
import 'package:pulse_mobile/widgets/pulse_card.dart';

/// 总览 / 报警页共用的「AI 洞察 / AI 复盘」卡：左侧渐变竖条 + 结论 + 操作。
class AiInsightCard extends StatelessWidget {
  const AiInsightCard({
    super.key,
    required this.text,
    this.highlights = const <String>[],
    this.actions = const <String>[],
    this.tag = 'AI 洞察',
    this.time,
    this.onAction,
    this.onTap,
  });

  final String text;
  final List<String> highlights;
  final List<String> actions;
  final String tag;
  final String? time;
  final ValueChanged<String>? onAction;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    // 左侧渐变竖条用 Stack 定位：IntrinsicHeight + Row(stretch) 在 Wrap 场景下会低估卡片高度，
    // 导致底部按钮被卡片裁掉（实测 8px+）。
    return PulseCard(
      padding: EdgeInsets.zero,
      onTap: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(PulseRadius.card - 1),
        child: Stack(
          children: <Widget>[
            const Positioned(
              left: 0,
              top: 0,
              bottom: 0,
              width: 3,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: PulseTheme.insightBarGradient,
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 13, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      const Icon(
                        Icons.auto_awesome_rounded,
                        size: 13,
                        color: PulseColors.accent,
                      ),
                      const SizedBox(width: 5),
                      Text(
                        tag,
                        style: PulseText.tag.copyWith(
                          color: PulseColors.accent,
                          letterSpacing: 0.4,
                        ),
                      ),
                      const Spacer(),
                      if (time != null) Text(time!, style: PulseText.meta),
                    ],
                  ),
                  const SizedBox(height: 7),
                  HighlightedText(
                    text,
                    highlights: highlights,
                    style: PulseText.body,
                  ),
                  if (actions.isNotEmpty) ...<Widget>[
                    const SizedBox(height: 11),
                    Wrap(
                      spacing: 7,
                      runSpacing: 7,
                      children: <Widget>[
                        for (int i = 0; i < actions.length; i++)
                          MiniButton(
                            label: actions[i],
                            primary: i == 0,
                            onPressed: onAction == null
                                ? null
                                : () => onAction!(actions[i]),
                          ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
