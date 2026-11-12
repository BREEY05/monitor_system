import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 把 [highlights] 里的片段加粗 + 主文字色，其余用 [style]。
/// 用于「3 号泵组振动上升…」「当前 33.2°C…」这类强调句。
class HighlightedText extends StatelessWidget {
  const HighlightedText(
    this.text, {
    super.key,
    this.highlights = const <String>[],
    this.style,
    this.emphasisStyle,
    this.maxLines,
  });

  final String text;
  final List<String> highlights;
  final TextStyle? style;
  final TextStyle? emphasisStyle;
  final int? maxLines;

  List<InlineSpan> _spans() {
    final TextStyle base = style ?? PulseText.body;
    final TextStyle emphasis = emphasisStyle ??
        base.copyWith(
          color: PulseColors.ink,
          fontWeight: FontWeight.w700,
        );
    if (highlights.isEmpty) {
      return <InlineSpan>[TextSpan(text: text, style: base)];
    }

    final List<InlineSpan> spans = <InlineSpan>[];
    int cursor = 0;
    while (cursor < text.length) {
      int nearest = -1;
      String hit = '';
      for (final String keyword in highlights) {
        final int index = text.indexOf(keyword, cursor);
        if (index >= 0 && (nearest < 0 || index < nearest)) {
          nearest = index;
          hit = keyword;
        }
      }
      if (nearest < 0) {
        spans.add(TextSpan(text: text.substring(cursor), style: base));
        break;
      }
      if (nearest > cursor) {
        spans.add(TextSpan(text: text.substring(cursor, nearest), style: base));
      }
      spans.add(TextSpan(text: hit, style: emphasis));
      cursor = nearest + hit.length;
    }
    return spans;
  }

  @override
  Widget build(BuildContext context) {
    return Text.rich(
      TextSpan(children: _spans()),
      maxLines: maxLines,
      overflow: maxLines == null ? TextOverflow.clip : TextOverflow.ellipsis,
    );
  }
}
