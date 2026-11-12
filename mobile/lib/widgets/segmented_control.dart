import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 分段控件（列表 / 地图 / 巡检）。
class SegmentedControl extends StatelessWidget {
  const SegmentedControl({
    super.key,
    required this.segments,
    required this.index,
    required this.onChanged,
  });

  final List<String> segments;
  final int index;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 34,
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: PulseColors.segmentBg,
        borderRadius: BorderRadius.circular(PulseRadius.segment),
      ),
      child: Row(
        children: <Widget>[
          for (int i = 0; i < segments.length; i++)
            Expanded(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => onChanged(i),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 160),
                  curve: Curves.easeOut,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: i == index ? PulseColors.card : Colors.transparent,
                    borderRadius: BorderRadius.circular(9),
                    boxShadow:
                        i == index ? PulseShadow.card : const <BoxShadow>[],
                  ),
                  child: Text(
                    segments[i],
                    style: PulseText.chip.copyWith(
                      color: i == index ? PulseColors.ink : PulseColors.sub,
                      fontWeight:
                          i == index ? FontWeight.w600 : FontWeight.w500,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
