import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/data/mock_data.dart';
import 'package:pulse_mobile/models/device.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';
import 'package:pulse_mobile/widgets/pulse_card.dart';
import 'package:pulse_mobile/widgets/sparkline.dart';

/// AI 结构化回答的结论卡：结论标题 + 关注标记 + 三项实时指标。
class AiConclusionCard extends StatelessWidget {
  const AiConclusionCard({super.key});

  @override
  Widget build(BuildContext context) {
    return PulseCard(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Expanded(
                child: Text(
                  MockData.aiConclusionTitle,
                  style:
                      PulseText.cardTitle.copyWith(fontSize: 14, height: 1.35),
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: PulseColors.amberSoft,
                  borderRadius: BorderRadius.circular(PulseRadius.chip),
                  border: Border.all(color: PulseColors.amberLine),
                ),
                child: Text(
                  MockData.aiConclusionBadge,
                  style: PulseText.tag.copyWith(
                    fontSize: 9,
                    color: PulseColors.amberInk,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          const Text(MockData.aiConclusionSub, style: PulseText.bodySub),
          const SizedBox(height: 11),
          Container(height: 1, color: PulseColors.line2),
          const SizedBox(height: 10),
          Row(
            children: <Widget>[
              for (int i = 0;
                  i < MockData.twinFocusMetrics.length;
                  i++) ...<Widget>[
                if (i > 0)
                  Container(
                    width: 1,
                    height: 24,
                    margin: const EdgeInsets.symmetric(horizontal: 12),
                    color: PulseColors.line2,
                  ),
                Expanded(
                  child: _MiniMetric(metric: MockData.twinFocusMetrics[i]),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _MiniMetric extends StatelessWidget {
  const _MiniMetric({required this.metric});

  final DeviceMetric metric;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(metric.label, style: PulseText.meta.copyWith(fontSize: 9)),
        const SizedBox(height: 3),
        Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: <Widget>[
            Flexible(
              child: Text(
                metric.value,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: PulseText.miniValue.copyWith(fontSize: 15),
              ),
            ),
            const SizedBox(width: 2),
            Text(
              metric.unit,
              style: PulseText.meta.copyWith(fontSize: 8.5),
            ),
          ],
        ),
      ],
    );
  }
}

/// AI 回答中的 24h 趋势卡：折线 + 阈值虚线 + 图例。
class AiTrendCard extends StatelessWidget {
  const AiTrendCard({super.key});

  @override
  Widget build(BuildContext context) {
    return PulseCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                MockData.aiChartTitle,
                style: PulseText.cardTitle.copyWith(fontSize: 11.5),
              ),
              const Spacer(),
              Container(width: 10, height: 2, color: PulseColors.accent),
              const SizedBox(width: 4),
              Text('振动', style: PulseText.meta.copyWith(fontSize: 8.5)),
              const SizedBox(width: 8),
              Container(width: 10, height: 1, color: PulseColors.amber),
              const SizedBox(width: 4),
              Text('阈值', style: PulseText.meta.copyWith(fontSize: 8.5)),
            ],
          ),
          const SizedBox(height: 8),
          const Sparkline(
            values: MockData.aiTrend,
            color: PulseColors.accent,
            height: 56,
            lineWidth: 1.8,
            showEndDot: true,
            thresholdFraction: 0.24,
          ),
        ],
      ),
    );
  }
}
