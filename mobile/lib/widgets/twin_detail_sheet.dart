import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/data/mock_data.dart';
import 'package:pulse_mobile/models/device.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';
import 'package:pulse_mobile/widgets/mini_button.dart';
import 'package:pulse_mobile/widgets/sparkline.dart';

/// 数字孪生底部设备 sheet：标题 / 状态 / 三指标 / 24h 趋势 / 操作按钮。
class TwinDetailSheet extends StatelessWidget {
  const TwinDetailSheet({
    super.key,
    required this.spot,
    required this.onAiDiagnose,
    required this.onDetail,
    required this.onViewTrend,
    required this.onCube,
  });

  final TwinSpot spot;
  final VoidCallback onAiDiagnose;
  final VoidCallback onDetail;
  final VoidCallback onViewTrend;
  final VoidCallback onCube;

  @override
  Widget build(BuildContext context) {
    final bool alert = spot.state != TwinState.running;
    final String stateText = spot.state == TwinState.maintenance
        ? '维护中'
        : spot.state == TwinState.watch
            ? '关注'
            : '运行正常';
    final Color stateColor = spot.state == TwinState.running
        ? PulseColors.greenInk
        : PulseColors.amberInk;
    final Color stateBg = spot.state == TwinState.running
        ? PulseColors.greenSoft
        : PulseColors.amberSoft;
    final String note = alert ? MockData.twinFocusNote : '温度、电流稳定 · 数据实时同步';

    return Container(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.97),
        borderRadius: const BorderRadius.vertical(
          top: Radius.circular(PulseRadius.sheet),
        ),
        boxShadow: PulseShadow.sheet,
      ),
      padding: const EdgeInsets.fromLTRB(18, 8, 18, 10),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Center(
            child: Container(
              width: 34,
              height: 4,
              decoration: BoxDecoration(
                color: PulseColors.line,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 10),
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: <Widget>[
              Flexible(
                child: Text(
                  spot.name,
                  style: PulseText.sheetValue.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (spot.id == 'spot-pump') ...<Widget>[
                const SizedBox(width: 7),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: PulseColors.card2,
                    borderRadius: BorderRadius.circular(PulseRadius.tiny),
                    border: Border.all(color: PulseColors.line),
                  ),
                  child: const Text(MockData.twinFocusTag,
                      style: PulseText.labelDim),
                ),
              ],
              const Spacer(),
              GestureDetector(
                onTap: onDetail,
                child: const Row(
                  children: <Widget>[
                    Text('详情', style: PulseText.labelDim),
                    Icon(
                      Icons.chevron_right_rounded,
                      size: 14,
                      color: PulseColors.chevron,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 7),
          Row(
            children: <Widget>[
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: stateBg,
                  borderRadius: BorderRadius.circular(PulseRadius.small),
                ),
                child: Text(
                  stateText,
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.w700,
                    color: stateColor,
                    height: 1.2,
                  ),
                ),
              ),
              const SizedBox(width: 7),
              Flexible(
                child: Text(
                  note,
                  style: PulseText.meta.copyWith(color: PulseColors.sub),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: 11),
          Container(
            padding: const EdgeInsets.symmetric(vertical: 10),
            decoration: const BoxDecoration(
              border: Border(
                top: BorderSide(color: PulseColors.line2),
                bottom: BorderSide(color: PulseColors.line2),
              ),
            ),
            child: Row(
              children: <Widget>[
                for (int i = 0; i < MockData.twinFocusMetrics.length; i++)
                  Expanded(
                    child: _SheetMetric(
                      metric: MockData.twinFocusMetrics[i],
                      accent: i == 0 && alert,
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 10),
          const Row(
            children: <Widget>[
              Text(MockData.twinTrendTitle, style: PulseText.labelDim),
              Spacer(),
              Text(MockData.twinThreshold, style: PulseText.labelDim),
            ],
          ),
          const SizedBox(height: 4),
          const Sparkline(
            values: MockData.twinVibration,
            color: PulseColors.accent,
            height: 46,
            thresholdFraction: 0.18,
            showEndDot: true,
          ),
          const SizedBox(height: 10),
          Row(
            children: <Widget>[
              Expanded(
                flex: 5,
                child: MiniButton(
                  label: 'AI 诊断',
                  primary: true,
                  icon: Icons.auto_awesome_rounded,
                  height: 46,
                  fontSize: 11,
                  onPressed: onAiDiagnose,
                ),
              ),
              const SizedBox(width: 7),
              Expanded(
                flex: 4,
                child: MiniButton(
                  label: '查看趋势',
                  height: 46,
                  fontSize: 11,
                  onPressed: onViewTrend,
                ),
              ),
              const SizedBox(width: 7),
              _CubeButton(onTap: onCube),
            ],
          ),
        ],
      ),
    );
  }
}

class _SheetMetric extends StatelessWidget {
  const _SheetMetric({required this.metric, required this.accent});

  final DeviceMetric metric;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(metric.label, style: PulseText.labelDim),
        const SizedBox(height: 3),
        Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: <Widget>[
            Text(
              metric.value,
              style: TextStyle(
                fontSize: 19,
                fontWeight: FontWeight.w800,
                height: 1.1,
                color: accent ? PulseColors.amberInk : PulseColors.ink,
                fontFeatures: PulseText.tabular,
              ),
            ),
            const SizedBox(width: 2),
            Text(metric.unit, style: PulseText.tinyValue),
          ],
        ),
      ],
    );
  }
}

class _CubeButton extends StatelessWidget {
  const _CubeButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 46,
        height: 46,
        decoration: BoxDecoration(
          color: PulseColors.card,
          borderRadius: BorderRadius.circular(PulseRadius.chip),
          border: Border.all(color: PulseColors.line),
        ),
        child: const Icon(
          Icons.view_in_ar_outlined,
          size: 20,
          color: PulseColors.ink,
        ),
      ),
    );
  }
}
