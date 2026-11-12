import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/core/live_data.dart';
import 'package:pulse_mobile/core/live_view.dart';
import 'package:pulse_mobile/data/mock_data.dart';
import 'package:pulse_mobile/models/device.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';
import 'package:pulse_mobile/widgets/device_card.dart';
import 'package:pulse_mobile/widgets/pulse_card.dart';
import 'package:pulse_mobile/widgets/pulse_icon_button.dart';
import 'package:pulse_mobile/widgets/scan_card.dart';
import 'package:pulse_mobile/widgets/segmented_control.dart';
import 'package:pulse_mobile/widgets/status_chip.dart';
import 'package:pulse_mobile/widgets/workshop_map.dart';

/// 03 / 设备：列表 / 地图 / 巡检三种视图，地图与设备卡进入数字孪生。
class DevicesScreen extends StatefulWidget {
  const DevicesScreen({super.key, this.onOpenTwin, this.onOpenAi});

  final VoidCallback? onOpenTwin;
  final VoidCallback? onOpenAi;

  @override
  State<DevicesScreen> createState() => _DevicesScreenState();
}

class _DevicesScreenState extends State<DevicesScreen> {
  int _segment = 0;

  void _toast(String feature) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(feature), behavior: SnackBarBehavior.floating),
    );
  }

  @override
  Widget build(BuildContext context) {
    final PulseData data = PulseData.instance;
    return AnimatedBuilder(
      animation: data,
      builder: (BuildContext context, Widget? child) {
        final LiveSnapshot? snapshot = data.snapshot;
        final List<Device> devices = LiveView.devices(snapshot);
        return SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(18, 6, 18, 150),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  const Expanded(
                    child: Text('设备', style: PulseText.pageTitle),
                  ),
                  PulseIconButton(
                    icon: Icons.search_rounded,
                    onTap: () => _toast('设备搜索将在后续版本开放'),
                  ),
                  const SizedBox(width: 8),
                  PulseIconButton(
                    icon: Icons.qr_code_scanner_rounded,
                    onTap: () => _toast('扫码接入在后续版本开放'),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              SegmentedControl(
                segments: const <String>['列表', '地图', '巡检'],
                index: _segment,
                onChanged: (int value) => setState(() => _segment = value),
              ),
              const SizedBox(height: 10),
              _SummaryRow(snapshot: snapshot, data: data),
              const SizedBox(height: 10),
              if (_segment == 0) ...<Widget>[
                if (devices.isEmpty)
                  PulseCard(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 14),
                    child: Text(
                      data.loading ? '正在同步设备列表…' : '服务器还没有配置设备',
                      style: PulseText.bodySub,
                    ),
                  )
                else
                  for (final Device device in devices) ...<Widget>[
                    DeviceCard(device: device, onTap: widget.onOpenTwin),
                    const SizedBox(height: 8),
                  ],
                const SizedBox(height: 2),
                _MapCard(onTap: widget.onOpenTwin),
                const SizedBox(height: 9),
                ScanCard(onTap: widget.onOpenTwin),
              ] else if (_segment == 1) ...<Widget>[
                _MapCard(onTap: widget.onOpenTwin, height: 268),
                const SizedBox(height: 10),
                _ZoneLegend(devices: devices, onOpenTwin: widget.onOpenTwin),
                const SizedBox(height: 9),
                ScanCard(onTap: widget.onOpenTwin),
              ] else ...<Widget>[
                const _InspectionList(),
              ],
            ],
          ),
        );
      },
    );
  }
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow({required this.snapshot, required this.data});

  final LiveSnapshot? snapshot;
  final PulseData data;

  @override
  Widget build(BuildContext context) {
    final int online = snapshot?.onlineCount ?? 0;
    final int total = snapshot?.totalCount ?? 0;
    final int maintenance = snapshot?.devices
            .where((LiveDevice device) => device.status.contains('维护'))
            .length ??
        0;
    final int offline = total - online < 0 ? 0 : total - online;
    return Row(
      children: <Widget>[
        _SummaryItem(
          label: '在线',
          value: online.toString(),
          color: PulseColors.greenInk,
        ),
        const SizedBox(width: 10),
        _SummaryItem(
          label: '维护',
          value: maintenance.toString(),
          color: PulseColors.amberInk,
        ),
        const SizedBox(width: 10),
        _SummaryItem(
          label: '离线',
          value: offline.toString(),
          color: PulseColors.dim,
        ),
        const Spacer(),
        Text(
          '同步 ${data.latencyMs}ms',
          style: PulseText.meta.copyWith(fontSize: 9.5),
        ),
      ],
    );
  }
}

class _SummaryItem extends StatelessWidget {
  const _SummaryItem({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Text(label, style: PulseText.meta.copyWith(fontSize: 9.5)),
        const SizedBox(width: 3),
        Text(
          value,
          style: PulseText.tinyValue.copyWith(
            fontSize: 10.5,
            color: color,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }
}

class _MapCard extends StatelessWidget {
  const _MapCard({required this.onTap, this.height = 156});

  final VoidCallback? onTap;
  final double height;

  @override
  Widget build(BuildContext context) {
    return PulseCard(
      padding: EdgeInsets.zero,
      onTap: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(PulseRadius.card),
        child: SizedBox(
          height: height,
          width: double.infinity,
          child: const WorkshopMap(),
        ),
      ),
    );
  }
}

class _ZoneLegend extends StatelessWidget {
  const _ZoneLegend({required this.devices, this.onOpenTwin});

  final List<Device> devices;
  final VoidCallback? onOpenTwin;

  static const List<Color> _zoneColors = <Color>[
    PulseColors.accent,
    PulseColors.green,
    PulseColors.amber,
  ];

  @override
  Widget build(BuildContext context) {
    final Map<String, int> counts = <String, int>{};
    for (final Device device in devices) {
      final String zone = device.subtitle.split(' · ').first;
      counts[zone] = (counts[zone] ?? 0) + 1;
    }
    final List<String> zones = counts.keys.take(3).toList();
    return PulseCard(
      padding: const EdgeInsets.fromLTRB(13, 11, 13, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                '车间分区',
                style: PulseText.cardTitle.copyWith(fontSize: 11.5),
              ),
              const Spacer(),
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: onOpenTwin,
                child: Row(
                  children: <Widget>[
                    Text(
                      '进入数字孪生',
                      style: PulseText.meta.copyWith(
                        fontSize: 9,
                        fontWeight: FontWeight.w600,
                        color: PulseColors.accentInk,
                      ),
                    ),
                    const Icon(
                      Icons.chevron_right_rounded,
                      size: 14,
                      color: PulseColors.accentInk,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 9),
          if (zones.isEmpty)
            Text('暂无设备分区数据', style: PulseText.meta.copyWith(fontSize: 9))
          else
            Row(
              children: <Widget>[
                for (int i = 0; i < zones.length; i++) ...<Widget>[
                  if (i > 0) const SizedBox(width: 7),
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 9,
                      ),
                      decoration: BoxDecoration(
                        color: _zoneColors[i % 3].withValues(alpha: 0.06),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: _zoneColors[i % 3].withValues(alpha: 0.18),
                        ),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            zones[i],
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: PulseText.meta.copyWith(fontSize: 9),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            '${counts[zones[i]]} 台',
                            style: PulseText.miniValue.copyWith(
                              fontSize: 13,
                              color: _zoneColors[i % 3],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ],
            ),
          const SizedBox(height: 9),
          Text(
            '点击任意设备卡或地图进入 WebView 版 Three.js 数字孪生',
            style: PulseText.meta.copyWith(fontSize: 8.5),
          ),
        ],
      ),
    );
  }
}

class _InspectionList extends StatelessWidget {
  const _InspectionList();

  @override
  Widget build(BuildContext context) {
    return PulseCard(
      padding: const EdgeInsets.fromLTRB(13, 12, 13, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                '今日巡检',
                style: PulseText.cardTitle.copyWith(fontSize: 11.5),
              ),
              const Spacer(),
              Text(
                '4 项 · 完成 2',
                style: PulseText.meta.copyWith(fontSize: 9),
              ),
            ],
          ),
          const SizedBox(height: 4),
          for (int i = 0; i < MockData.inspectionTasks.length; i++)
            _InspectionRow(
              task: MockData.inspectionTasks[i],
              showDivider: i != MockData.inspectionTasks.length - 1,
            ),
          const SizedBox(height: 6),
          Text(
            '巡检工单将在后续版本接入后端',
            style: PulseText.meta.copyWith(fontSize: 8.5),
          ),
        ],
      ),
    );
  }
}

class _InspectionRow extends StatelessWidget {
  const _InspectionRow({required this.task, required this.showDivider});

  final InspectionTask task;
  final bool showDivider;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(
        border: showDivider
            ? const Border(bottom: BorderSide(color: PulseColors.line2))
            : null,
      ),
      child: Row(
        children: <Widget>[
          Container(
            width: 30,
            height: 30,
            decoration: BoxDecoration(
              color: task.done ? PulseColors.greenSoft : PulseColors.accentSoft,
              borderRadius: BorderRadius.circular(9),
            ),
            child: Icon(
              task.done ? Icons.check_rounded : Icons.schedule_rounded,
              size: 15,
              color: task.done ? PulseColors.green : PulseColors.accent,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  task.title,
                  style: PulseText.listTitle.copyWith(
                    color: task.done ? PulseColors.sub : PulseColors.text,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  task.subtitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: PulseText.meta.copyWith(fontSize: 9),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: <Widget>[
              Text(task.time, style: PulseText.meta.copyWith(fontSize: 9)),
              const SizedBox(height: 3),
              StatusChip(
                label: task.status,
                color: task.done ? PulseColors.greenInk : PulseColors.accentInk,
                background:
                    task.done ? PulseColors.greenSoft : PulseColors.accentSoft,
                borderColor:
                    task.done ? PulseColors.greenLine : PulseColors.accentLine,
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                textStyle: PulseText.meta.copyWith(
                  fontSize: 8.5,
                  color:
                      task.done ? PulseColors.greenInk : PulseColors.accentInk,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
