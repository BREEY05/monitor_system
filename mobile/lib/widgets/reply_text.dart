import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 轻量 Markdown 渲染：只处理 Agent 回复里实际会出现的 **加粗**、行首 - 列表、
/// # 标题和空行分段，不引入额外依赖。
class ReplyText extends StatelessWidget {
  const ReplyText({super.key, required this.text, this.style});

  final String text;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    final TextStyle base = (style ?? PulseText.body)
        .copyWith(fontSize: 12.5, height: 1.7, color: PulseColors.text);
    final List<Widget> blocks = <Widget>[];
    for (final String raw in text.split('\n')) {
      final String line = raw.trimRight();
      if (line.trim().isEmpty) {
        blocks.add(const SizedBox(height: 6));
        continue;
      }
      final String trimmed = line.trimLeft();
      final bool bullet = trimmed.startsWith('- ') ||
          trimmed.startsWith('* ') ||
          trimmed.startsWith('• ');
      if (bullet) {
        blocks.add(
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Padding(
                  padding: const EdgeInsets.only(top: 6, right: 6),
                  child: Container(
                    width: 4,
                    height: 4,
                    decoration: const BoxDecoration(
                      color: PulseColors.accent,
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
                Expanded(
                  child: Text.rich(
                    TextSpan(
                      children: _spans(trimmed.substring(2), base),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
        continue;
      }
      // ### 标题、**整行加粗** 都按小标题处理。
      final String heading = trimmed.replaceFirst(RegExp(r'^#+\s*'), '');
      final bool isHeading =
          trimmed.startsWith('#') || RegExp(r'^\*\*.+\*\*$').hasMatch(trimmed);
      blocks.add(
        Padding(
          padding: EdgeInsets.only(bottom: isHeading ? 5 : 2),
          child: Text.rich(
            TextSpan(
              children: _spans(heading, base),
            ),
            style: isHeading
                ? base.copyWith(fontWeight: FontWeight.w700, fontSize: 13)
                : base,
          ),
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: blocks,
    );
  }

  /// 把 **xx** 拆成加粗片段，其余保持普通文本。
  static List<InlineSpan> _spans(String raw, TextStyle base) {
    final List<InlineSpan> spans = <InlineSpan>[];
    final RegExp pattern = RegExp(r'\*\*(.+?)\*\*');
    int cursor = 0;
    for (final RegExpMatch match in pattern.allMatches(raw)) {
      if (match.start > cursor) {
        spans.add(TextSpan(text: raw.substring(cursor, match.start)));
      }
      spans.add(
        TextSpan(
          text: match.group(1),
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
      );
      cursor = match.end;
    }
    if (cursor < raw.length) {
      spans.add(TextSpan(text: raw.substring(cursor)));
    }
    if (spans.isEmpty) {
      spans.add(TextSpan(text: raw));
    }
    return spans;
  }
}
