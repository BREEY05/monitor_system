import 'package:material_ui/material_ui.dart';

/// 指标趋势方向，用于给脚注上色（温度正常用绿、振动上升用琥珀）。
enum MetricTrend { up, down, flat }

/// 总览 2×2 指标卡的一条数据。
class Metric {
  const Metric({
    required this.label,
    required this.value,
    required this.unit,
    required this.spark,
    required this.color,
    this.footnote,
    this.footnoteColor,
    this.trend = MetricTrend.flat,
  });

  final String label;
  final String value;
  final String unit;

  /// 归一化前的原始序列即可，Sparkline 会自动缩放。
  final List<double> spark;
  final Color color;
  final String? footnote;
  final Color? footnoteColor;
  final MetricTrend trend;
}
