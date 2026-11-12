import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/models/device.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';
import 'package:pulse_mobile/widgets/pulse_card.dart';
import 'package:pulse_mobile/widgets/sparkline.dart';

/// 设备列表卡：状态光晕 + 名称/编号 + 实时指标 + 迷你趋势。
class DeviceCard extends StatelessWidget {
  const DeviceCard({super.key, required this.device, this.onTap});

  final Device device;
  final VoidCallback? onTap;

  Color get _haloColor {
    switch (device.status) {
      case DeviceStatus.running:
        return device.sparkColor;
      case DeviceStatus.maintenance:
        return PulseColors.amber;
      case DeviceStatus.offline:
        return PulseColors.dim;
    }
  }

  @override
  Widget build(BuildContext context) {
    final Color halo = _haloColor;
    return PulseCard(
      onTap: onTap,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
      color: device.selected ? const Color(0xFFFCFDFF) : PulseColors.card,
      borderColor: device.selected ? const Color(0xFFC7D2FE) : PulseColors.line,
      child: Row(
        children: <Widget>[
          // 状态光晕：淡色圆底 + 同色内环 + 实心圆点（不使用图标，避免"齿轮"观感）。
          Container(
            width: 40,
            height: 40,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: halo.withValues(alpha: 0.08),
              shape: BoxShape.circle,
              border: Border.all(color: halo.withValues(alpha: 0.14)),
            ),
            child: Container(
              width: 20,
              height: 20,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(
                  color: halo.withValues(alpha: 0.30),
                  width: 1.5,
                ),
              ),
              child: Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(color: halo, shape: BoxShape.circle),
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Flexible(
                      child: Text(
                        device.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: PulseText.cardTitle.copyWith(fontSize: 11.5),
                      ),
                    ),
                    if (device.tag != null) ...<Widget>[
                      const SizedBox(width: 5),
                      DeviceTag(label: device.tag!, status: device.status),
                    ],
                  ],
                ),
                const SizedBox(height: 3),
                Text(
                  device.subtitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: PulseText.meta.copyWith(fontSize: 9),
                ),
                const SizedBox(height: 6),
                if (device.metrics.isEmpty)
                  Text(
                    '暂无实时数据 · 车间级指标见总览',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: PulseText.meta.copyWith(
                      fontSize: 9,
                      color: PulseColors.dim,
                    ),
                  )
                else
                  Wrap(
                    spacing: 10,
                    runSpacing: 2,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: <Widget>[
                      for (final DeviceMetric metric in device.metrics)
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.baseline,
                          textBaseline: TextBaseline.alphabetic,
                          children: <Widget>[
                            Text(
                              metric.label,
                              style: PulseText.meta.copyWith(fontSize: 8.5),
                            ),
                            const SizedBox(width: 3),
                            Text(
                              metric.value,
                              style:
                                  PulseText.tinyValue.copyWith(fontSize: 10.5),
                            ),
                            if (metric.unit.isNotEmpty) ...<Widget>[
                              const SizedBox(width: 1),
                              Text(
                                metric.unit,
                                style: PulseText.meta.copyWith(fontSize: 8),
                              ),
                            ],
                          ],
                        ),
                    ],
                  ),
              ],
            ),
          ),
          const SizedBox(width: 6),
          Sparkline(
            values: device.spark,
            color: device.sparkColor,
            width: 56,
            height: 34,
            lineWidth: 1.5,
          ),
        ],
      ),
    );
  }
}

/// 设备名后的状态标签（运行中 / 3D / 维护中）。
class DeviceTag extends StatelessWidget {
  const DeviceTag({super.key, required this.label, required this.status});

  final String label;
  final DeviceStatus status;

  @override
  Widget build(BuildContext context) {
    late final Color background;
    late final Color border;
    late final Color text;
    switch (status) {
      case DeviceStatus.running:
        if (label == '3D') {
          background = PulseColors.card2;
          border = PulseColors.line;
          text = PulseColors.sub;
        } else {
          background = PulseColors.accentSoft;
          border = PulseColors.accentLine;
          text = PulseColors.accentInk;
        }
        break;
      case DeviceStatus.maintenance:
        background = PulseColors.amberSoft;
        border = PulseColors.amberLine;
        text = PulseColors.amberInk;
        break;
      case DeviceStatus.offline:
        background = PulseColors.card2;
        border = PulseColors.line;
        text = PulseColors.dim;
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: border),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 8.5,
          height: 1.2,
          fontWeight: FontWeight.w600,
          color: text,
        ),
      ),
    );
  }
}
