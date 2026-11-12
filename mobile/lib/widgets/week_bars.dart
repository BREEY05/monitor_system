import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 近 7 天报警柱状图（纯 Flutter 布局，不做交互）。
class WeekBars extends StatelessWidget {
  const WeekBars({
    super.key,
    required this.bars,
    required this.labels,
    this.highlightIndex = -1,
    this.maxHeight = 52,
  });

  final List<double> bars;
  final List<String> labels;
  final int highlightIndex;
  final double maxHeight;

  @override
  Widget build(BuildContext context) {
    double maxValue = 1;
    for (final double value in bars) {
      if (value > maxValue) {
        maxValue = value;
      }
    }

    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: <Widget>[
        for (int i = 0; i < bars.length; i++)
          Expanded(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                SizedBox(
                  height: maxHeight,
                  child: Align(
                    alignment: Alignment.bottomCenter,
                    child: Container(
                      width: 10,
                      height: (bars[i] / maxValue) * maxHeight,
                      decoration: BoxDecoration(
                        color: i == highlightIndex
                            ? PulseColors.amber
                            : const Color(0xFFDDE3FF),
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 7),
                Text(
                  i < labels.length ? labels[i] : '',
                  style: PulseText.meta.copyWith(
                    color:
                        i == highlightIndex ? PulseColors.ink : PulseColors.dim,
                    fontWeight:
                        i == highlightIndex ? FontWeight.w600 : FontWeight.w400,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
