import 'package:material_ui/material_ui.dart';

/// 设备状态：与后端 status 字段（运行中 / 维护中 / 离线）对应。
enum DeviceStatus { running, maintenance, offline }

/// 设备卡右上角展示的一个读数，例如「振动 0.18 mm/s」。
class DeviceMetric {
  const DeviceMetric(this.label, this.value, this.unit);

  final String label;
  final String value;
  final String unit;
}

/// 设备列表 / 数字孪生共用的设备摘要。
class Device {
  const Device({
    required this.id,
    required this.name,
    required this.subtitle,
    required this.status,
    required this.metrics,
    required this.spark,
    required this.sparkColor,
    this.tag,
    this.selected = false,
  });

  final String id;
  final String name;
  final String? tag;
  final String subtitle;
  final DeviceStatus status;
  final List<DeviceMetric> metrics;
  final List<double> spark;
  final Color sparkColor;
  final bool selected;
}

/// 数字孪生场景里的车间分区。
class TwinZone {
  const TwinZone({
    required this.id,
    required this.name,
    required this.count,
    required this.color,
  });

  final String id;
  final String name;
  final int count;
  final Color color;
}

/// 数字孪生场景里设备的状态（与图例一致）。
enum TwinState { running, watch, maintenance }

/// 数字孪生场景中的设备热点。
/// [dx] / [dy] 是热点在场景画布中的归一化比例（0–1），用于同时定位
/// CustomPainter 绘制的设备与浮在上层的标签。
class TwinSpot {
  const TwinSpot({
    required this.id,
    required this.name,
    required this.zoneId,
    required this.state,
    required this.dx,
    required this.dy,
    this.note,
    this.selected = false,
  });

  final String id;
  final String name;
  final String zoneId;
  final TwinState state;
  final double dx;
  final double dy;
  final String? note;
  final bool selected;
}

/// 巡检 tab 里的一条巡检任务（M1 仅 Mock）。
class InspectionTask {
  const InspectionTask({
    required this.title,
    required this.subtitle,
    required this.time,
    required this.status,
    required this.done,
  });

  final String title;
  final String subtitle;
  final String time;
  final String status;
  final bool done;
}
