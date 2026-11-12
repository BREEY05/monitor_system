import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/models/metric.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';
import 'package:pulse_mobile/widgets/pulse_card.dart';
import 'package:pulse_mobile/widgets/sparkline.dart';

/// 总览 2×2 指标卡：标签 / 数值 + 单位 / 脚注 + 迷你折线。
class StatTile extends StatelessWidget {
  const StatTile({super.key, required this.metric, this.onTap});

  final Metric metric;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final Color footnoteColor = metric.footnoteColor ?? PulseColors.dim;
    // 缺失值不显示“-- °C”这种半截单位，统一降级成灰色的“暂无”。
    final bool empty = metric.value == '--';
    return PulseCard(
      onTap: onTap,
      padding: const EdgeInsets.fromLTRB(13, 11, 10, 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(metric.label, style: PulseText.label),
          const SizedBox(height: 5),
          if (empty)
            Text(
              '暂无',
              style: PulseText.metricValue.copyWith(
                fontSize: 17,
                fontWeight: FontWeight.w600,
                color: PulseColors.dim,
              ),
            )
          else
            Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: <Widget>[
                Text(metric.value, style: PulseText.metricValue),
                const SizedBox(width: 3),
                Text(metric.unit, style: PulseText.metricUnit),
              ],
            ),
          const Spacer(),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: <Widget>[
              Expanded(
                child: Row(
                  children: <Widget>[
                    if (metric.trend != MetricTrend.flat) ...<Widget>[
                      Icon(
                        metric.trend == MetricTrend.up
                            ? Icons.trending_up_rounded
                            : Icons.trending_down_rounded,
                        size: 11,
                        color: footnoteColor,
                      ),
                      const SizedBox(width: 2),
                    ],
                    Flexible(
                      child: Text(
                        metric.footnote ?? '',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: PulseText.tinyValue.copyWith(
                          fontSize: 9,
                          fontWeight: FontWeight.w600,
                          color: footnoteColor,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 4),
              Sparkline(
                values: metric.spark,
                color: metric.color,
                width: 54,
                height: 20,
                lineWidth: 1.5,
                area: false,
              ),
            ],
          ),
        ],
      ),
    );
  }
}
