import 'dart:math' as math;

import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/core/live_data.dart';
import 'package:pulse_mobile/core/session.dart';
import 'package:pulse_mobile/models/alert_item.dart';
import 'package:pulse_mobile/models/device.dart';
import 'package:pulse_mobile/models/metric.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 把 /api/twin/overview 的实时快照翻译成 M1 就已定型的视图模型，
/// 这样 UI 组件（StatTile / DeviceCard / AlertItem）不用改签名。
class LiveView {
  const LiveView._();

  static String greet() {
    final int hour = DateTime.now().hour;
    final String prefix = hour < 6
        ? '凌晨好'
        : hour < 11
            ? '早上好'
            : hour < 14
                ? '中午好'
                : hour < 18
                    ? '下午好'
                    : '晚上好';
    return '$prefix，${Session.instance.displayName}';
  }

  static String location(LiveSnapshot? snapshot) {
    final String area = snapshot == null || snapshot.sourceLabel.isEmpty
        ? '一号车间'
        : snapshot.sourceLabel;
    return '上海 · $area · 实时';
  }

  /// 缺失值统一显示 --，避免出现 NaN 或空白。
  static String value(double? raw, {int digits = 1}) {
    if (raw == null || raw.isNaN) {
      return '--';
    }
    if (digits == 0) {
      return raw.round().toString();
    }
    return raw.toStringAsFixed(digits);
  }

  static List<double> sparkOf(PulseData data, String key) {
    final List<double> history = data.history(key);
    if (history.length >= 3) {
      return history;
    }
    // 还没有历史时给一条平稳的示意线，避免指标卡右侧出现空洞。
    // 用 key 派生相位与振幅，让四张指标卡形状各不相同，且同一 key 每次渲染稳定。
    final double base = history.isEmpty ? 1 : history.last;
    final int seed = key.codeUnits.fold<int>(0, (int a, int b) => a + b * 7);
    final double phase = (seed % 23) * 0.29;
    final double amp = 0.010 + (seed % 5) * 0.004;
    return List<double>.generate(8, (int i) {
      final double t = i.toDouble();
      final double wave = 0.62 * math.sin(t * 0.62 + phase) +
          0.30 * math.sin(t * 1.35 + phase * 1.7) +
          0.18 * math.cos(t * 2.10 + phase * 0.6);
      return base * (1 + amp * wave);
    });
  }

  static List<Metric> metrics(LiveSnapshot? snapshot) {
    final PulseData data = PulseData.instance;
    final double? temp = snapshot?.temperature;
    final double? humidity = snapshot?.humidity;
    final double? pressure = snapshot?.pressure;
    final double? vibration = snapshot?.vibration;
    final double? tempThreshold = snapshot?.thresholdTemperature;
    final double? humidityThreshold = snapshot?.thresholdHumidity;
    final double? vibrationThreshold = snapshot?.thresholdVibration;
    final bool tempOver =
        temp != null && tempThreshold != null && temp > tempThreshold;
    final bool humidityOver = humidity != null &&
        humidityThreshold != null &&
        humidity > humidityThreshold;
    final bool vibrationOver = vibration != null &&
        vibrationThreshold != null &&
        vibration > vibrationThreshold;

    return <Metric>[
      Metric(
        label: '温度',
        value: value(temp),
        unit: '°C',
        footnote: tempThreshold == null ? '暂无阈值' : '阈值 ${value(tempThreshold)}',
        footnoteColor: tempOver ? PulseColors.red : PulseColors.green,
        spark: sparkOf(data, 'temperature'),
        color: tempOver ? PulseColors.red : PulseColors.green,
        trend: tempOver ? MetricTrend.up : MetricTrend.down,
      ),
      Metric(
        label: '湿度',
        value: value(humidity),
        unit: '%',
        footnote: humidityThreshold == null
            ? '暂无阈值'
            : '阈值 ${value(humidityThreshold)}',
        footnoteColor: humidityOver ? PulseColors.red : PulseColors.dim,
        spark: sparkOf(data, 'humidity'),
        color: PulseColors.accent,
      ),
      Metric(
        label: '气压',
        value: value(pressure, digits: 0),
        unit: 'hPa',
        footnote: pressure == null ? '暂无数据' : '稳定',
        spark: sparkOf(data, 'pressure'),
        color: PulseColors.purple,
      ),
      Metric(
        label: '振动',
        value: value(vibration, digits: 2),
        unit: 'mm/s',
        footnote: vibrationThreshold == null
            ? '暂无阈值'
            : (vibrationOver
                ? '超过阈值'
                : '阈值 ${value(vibrationThreshold, digits: 2)}'),
        footnoteColor: vibrationOver ? PulseColors.amber : PulseColors.amber,
        spark: sparkOf(data, 'vibration'),
        color: PulseColors.amber,
        trend: vibrationOver ? MetricTrend.up : MetricTrend.flat,
      ),
    ];
  }

  static DeviceStatus _statusOf(LiveDevice device) {
    final String status = device.status;
    if (!device.online || status.contains('离线') || status.contains('offline')) {
      return DeviceStatus.offline;
    }
    if (status.contains('维护') || status.contains('maintenance')) {
      return DeviceStatus.maintenance;
    }
    return DeviceStatus.running;
  }

  static List<Device> devices(LiveSnapshot? snapshot) {
    if (snapshot == null) {
      return const <Device>[];
    }
    final PulseData data = PulseData.instance;
    return snapshot.devices.map((LiveDevice device) {
      // 设备卡用各自的 key 生成示意线，避免七张卡折线形状完全一样。
      final List<double> spark = sparkOf(data, 'vibration:${device.id}');
      final DeviceStatus status = _statusOf(device);
      final Color sparkColor = status == DeviceStatus.offline
          ? PulseColors.dim
          : status == DeviceStatus.maintenance
              ? PulseColors.amber
              : PulseColors.accent;
      final String? tag =
          device.riskLevel == 'critical' || device.riskLevel == 'high'
              ? '告警'
              : device.sensorBound
                  ? '设备传感器'
                  : null;
      return Device(
        id: device.id,
        name: device.name,
        tag: tag,
        subtitle:
            '${device.station.isEmpty ? '工位 ${device.index + 1}' : device.station} · ${device.status.isEmpty ? '状态未知' : device.status}',
        status: status,
        metrics: <DeviceMetric>[
          if (snapshot.vibration != null)
            DeviceMetric('振动', value(snapshot.vibration, digits: 2), 'mm/s'),
          if (snapshot.temperature != null)
            DeviceMetric('温度', value(snapshot.temperature), '°C'),
        ],
        spark: spark,
        sparkColor: sparkColor,
      );
    }).toList();
  }

  static AlertLevel _levelOf(String level) {
    if (level == 'critical' || level == 'severe') {
      return AlertLevel.critical;
    }
    if (level == 'warning') {
      return AlertLevel.warning;
    }
    return AlertLevel.info;
  }

  /// 报警 id 是后端整数，UI 的 AlertItem.id 是字符串；处理时用这个映射找回。
  static int? alertIdOf(AlertItem item) {
    final String raw = item.id.replaceFirst('alert-', '');
    return int.tryParse(raw);
  }

  static List<AlertItem> alerts(LiveSnapshot? snapshot) {
    if (snapshot == null) {
      return const <AlertItem>[];
    }
    return snapshot.alerts.map((LiveAlert alert) {
      final AlertLevel level = _levelOf(alert.level);
      final List<String> parts = <String>[];
      if (alert.source.isNotEmpty) {
        parts.add(alert.source);
      }
      if (alert.value != null) {
        parts.add(
            '当前 ${value(alert.value, digits: alert.value == alert.value!.roundToDouble() ? 0 : 2)}');
      }
      if (alert.threshold != null) {
        parts.add('阈值 ${value(alert.threshold, digits: 1)}');
      }
      if (alert.time.isNotEmpty) {
        parts.add(alert.time);
      }
      final List<String> actions = level == AlertLevel.critical
          ? <String>['处理', '追问 AI']
          : <String>['查看趋势'];
      return AlertItem(
        id: alert.id == null ? 'alert-temp' : 'alert-${alert.id}',
        title: alert.title,
        level: level,
        time: alert.time,
        subtitle: parts.isEmpty ? '来源未知' : parts.join(' · '),
        highlights: alert.value == null
            ? const <String>[]
            : <String>[value(alert.value, digits: 1)],
        actions: alert.handled ? const <String>[] : actions,
        primaryAction: level == AlertLevel.critical ? '处理' : null,
      );
    }).toList();
  }

  /// 总览 AI 洞察：没有报警时给运维建议，有报警时指向最近一条。
  static String insightText(LiveSnapshot? snapshot) {
    if (snapshot == null) {
      return '正在同步车间实时数据，稍候会给出运行结论与巡检建议。';
    }
    final List<LiveAlert> alerts = snapshot.alerts;
    if (alerts.isEmpty) {
      if (!snapshot.sourceOnline) {
        return '车间暂无实时上报，数据可能来自缓存。请检查网关与传感器连接。';
      }
      return '当前 ${snapshot.onlineCount}/${snapshot.totalCount} 台设备在线，温度 ${value(snapshot.temperature)} °C，振动 ${value(snapshot.vibration, digits: 2)} mm/s，未发现需要立即处理的异常。';
    }
    final LiveAlert first = alerts.first;
    return '检测到 ${alerts.length} 条未处理报警，最近一条为「${first.title}」。建议先确认设备状态，再决定是否停机检查。';
  }

  static List<String> insightHighlights(LiveSnapshot? snapshot) {
    if (snapshot == null || snapshot.alerts.isEmpty) {
      return const <String>[];
    }
    return <String>['「${snapshot.alerts.first.title}」'];
  }

  static List<String> insightActions(LiveSnapshot? snapshot) {
    return snapshot != null && snapshot.alerts.isNotEmpty
        ? const <String>['追问 AI', '查看设备', '忽略']
        : const <String>['追问 AI', '查看设备'];
  }

  static String deviceRatio(LiveSnapshot? snapshot) {
    if (snapshot == null) {
      return '--/-- 设备';
    }
    return '${snapshot.onlineCount}/${snapshot.totalCount} 设备';
  }

  static String latency(PulseData data) {
    return '延迟 ${data.latencyMs}ms';
  }
}
