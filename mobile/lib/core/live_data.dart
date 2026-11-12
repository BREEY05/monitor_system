import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'package:pulse_mobile/core/api_client.dart';
import 'package:pulse_mobile/core/session.dart';

/// 一台设备的实时摘要（来自 /api/twin/overview）。
class LiveDevice {
  LiveDevice({
    required this.id,
    required this.name,
    required this.status,
    required this.online,
    required this.station,
    required this.sensorBound,
    required this.openAlerts,
    required this.riskLevel,
    required this.modelUrl,
    required this.index,
  });

  final String id;
  final String name;
  final String status;
  final bool online;
  final String station;
  final bool sensorBound;
  final int openAlerts;
  final String riskLevel;
  final String modelUrl;
  final int index;

  factory LiveDevice.fromJson(Map<String, dynamic> json) {
    final Object? risk = json['risk'];
    final Object? alerts = json['alerts'];
    return LiveDevice(
      id: (json['id'] ?? '').toString(),
      name: (json['name'] ?? '').toString(),
      status: (json['status'] ?? '').toString(),
      online: json['online'] == true,
      station: (json['station'] ?? '').toString(),
      sensorBound: json['sensor_bound'] == true,
      openAlerts: alerts is Map ? _asInt(alerts['open']) : 0,
      riskLevel:
          risk is Map ? (risk['level'] ?? 'normal').toString() : 'normal',
      modelUrl: (json['model_url'] ?? '').toString(),
      index: _asInt(json['index']),
    );
  }
}

/// 报警条目（overview 只给未处理报警）。
class LiveAlert {
  LiveAlert({
    required this.id,
    required this.title,
    required this.level,
    required this.time,
    required this.source,
    required this.deviceId,
    required this.type,
    required this.value,
    required this.threshold,
    required this.handled,
  });

  final int? id;
  final String title;
  final String level;
  final String time;
  final String source;
  final String deviceId;
  final String type;
  final double? value;
  final double? threshold;
  final bool handled;

  bool get isCritical => level == 'critical' || level == 'severe';
  bool get isWarning => level == 'warning';

  factory LiveAlert.fromJson(Map<String, dynamic> json) {
    return LiveAlert(
      id: _asIntNullable(json['id']),
      title: (json['title'] ?? '设备告警').toString(),
      level: (json['level'] ?? 'warning').toString(),
      time: _formatTime(json['time']),
      source: (json['source'] ?? json['area'] ?? '').toString(),
      deviceId: (json['device_id'] ?? '').toString(),
      type: (json['type'] ?? '').toString(),
      value: _asDouble(json['value']),
      threshold: _asDouble(json['threshold']),
      handled: json['handled'] == true,
    );
  }
}

/// 一次 /api/twin/overview 的完整快照。
class LiveSnapshot {
  LiveSnapshot({
    required this.generatedAt,
    required this.sourceLabel,
    required this.sourceOnline,
    required this.stale,
    required this.temperature,
    required this.humidity,
    required this.pressure,
    required this.vibration,
    required this.thresholdTemperature,
    required this.thresholdHumidity,
    required this.thresholdVibration,
    required this.devices,
    required this.alerts,
    required this.openAlertTotal,
    required this.onlineCount,
    required this.totalCount,
    required this.dataOnline,
  });

  final DateTime generatedAt;
  final String sourceLabel;
  final bool sourceOnline;
  final bool stale;
  final double? temperature;
  final double? humidity;
  final double? pressure;
  final double? vibration;
  final double? thresholdTemperature;
  final double? thresholdHumidity;
  final double? thresholdVibration;
  final List<LiveDevice> devices;
  final List<LiveAlert> alerts;
  final int openAlertTotal;
  final int onlineCount;
  final int totalCount;
  final bool dataOnline;

  int get criticalCount => alerts.where((LiveAlert a) => a.isCritical).length;
  int get warningCount => alerts.where((LiveAlert a) => a.isWarning).length;
  int get infoCount =>
      alerts.where((LiveAlert a) => !a.isCritical && !a.isWarning).length;

  /// 健康分：在线率 70% + 未处理报警扣分 + 数据源在线加权。
  int get healthScore {
    double score = totalCount == 0 ? 80 : 70 * onlineCount / totalCount + 30;
    score -= openAlertTotal * 3.5;
    score -= criticalCount * 5;
    if (!sourceOnline) {
      score -= 12;
    }
    return score.clamp(35, 99).round();
  }

  factory LiveSnapshot.fromJson(Map<String, dynamic> json) {
    final Object? plant = json['plant'];
    final Map<String, dynamic> plantMap =
        plant is Map ? Map<String, dynamic>.from(plant) : <String, dynamic>{};
    final Object? thresholds = json['thresholds'];
    final Map<String, dynamic> thresholdMap = thresholds is Map
        ? Map<String, dynamic>.from(thresholds)
        : <String, dynamic>{};
    final Object? source = json['source'];
    final Map<String, dynamic> sourceMap =
        source is Map ? Map<String, dynamic>.from(source) : <String, dynamic>{};
    final Object? summary = json['summary'];
    final Map<String, dynamic> summaryMap = summary is Map
        ? Map<String, dynamic>.from(summary)
        : <String, dynamic>{};
    final Object? alerts = json['alerts'];
    final Map<String, dynamic> alertsMap =
        alerts is Map ? Map<String, dynamic>.from(alerts) : <String, dynamic>{};
    final Object? devices = json['devices'];
    final Object? items = alertsMap['items'];
    final List<LiveDevice> parsedDevices = devices is List
        ? devices
            .whereType<Map>()
            .map((Map item) =>
                LiveDevice.fromJson(Map<String, dynamic>.from(item)))
            .toList()
        : <LiveDevice>[];
    final List<LiveAlert> parsedAlerts = items is List
        ? items
            .whereType<Map>()
            .map((Map item) =>
                LiveAlert.fromJson(Map<String, dynamic>.from(item)))
            .toList()
        : <LiveAlert>[];
    return LiveSnapshot(
      generatedAt: DateTime.tryParse((json['generated_at'] ?? '').toString()) ??
          DateTime.now(),
      sourceLabel: (sourceMap['label'] ?? '暂无实时上报').toString(),
      sourceOnline: sourceMap['online'] == true,
      stale: sourceMap['stale'] == true,
      temperature: _asDouble(plantMap['temperature']),
      humidity: _asDouble(plantMap['humidity']),
      pressure: _asDouble(plantMap['pressure']),
      vibration: _asDouble(plantMap['vibration']),
      thresholdTemperature: _asDouble(thresholdMap['temperature']),
      thresholdHumidity: _asDouble(thresholdMap['humidity']),
      thresholdVibration: _asDouble(thresholdMap['vibration']),
      devices: parsedDevices,
      alerts: parsedAlerts,
      openAlertTotal: _asInt(alertsMap['open_total']),
      onlineCount: _asInt(summaryMap['online']),
      totalCount: _asInt(summaryMap['total']),
      dataOnline: summaryMap['data_online'] == true,
    );
  }
}

/// 前台数据仓库：轮询 /api/twin/overview，并用 WS 接收传感器与报警事件。
class PulseData extends ChangeNotifier {
  PulseData._();

  static final PulseData instance = PulseData._();

  static const Duration pollInterval = Duration(seconds: 15);

  LiveSnapshot? _snapshot;
  bool _loading = false;
  bool _started = false;
  String? _error;
  int _latencyMs = 0;
  DateTime? _fetchedAt;
  final Map<String, List<double>> _history = <String, List<double>>{};

  Timer? _pollTimer;
  Timer? _retryTimer;
  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _wsSub;
  bool _wsConnected = false;
  bool _disposed = false;

  LiveSnapshot? get snapshot => _snapshot;
  bool get loading => _loading;
  String? get error => _error;
  int get latencyMs => _latencyMs;
  DateTime? get fetchedAt => _fetchedAt;
  bool get wsConnected => _wsConnected;

  List<double> history(String key) =>
      List<double>.unmodifiable(_history[key] ?? const <double>[]);

  void start() {
    if (_started) {
      return;
    }
    _started = true;
    unawaited(refresh());
    _pollTimer = Timer.periodic(pollInterval, (_) => refresh());
    _connectWs();
  }

  void stop() {
    _started = false;
    _pollTimer?.cancel();
    _pollTimer = null;
    _retryTimer?.cancel();
    _retryTimer = null;
    unawaited(_wsSub?.cancel());
    _wsSub = null;
    _channel?.sink.close();
    _channel = null;
    _wsConnected = false;
  }

  Future<void> refresh() async {
    if (_disposed || _loading) {
      return;
    }
    if (Session.instance.token == null) {
      return;
    }
    _loading = true;
    final Stopwatch watch = Stopwatch()..start();
    try {
      final dynamic result = await ApiClient.instance.get('/api/twin/overview');
      if (result is Map) {
        final LiveSnapshot next =
            LiveSnapshot.fromJson(Map<String, dynamic>.from(result));
        _snapshot = next;
        _error = null;
        _recordHistory(next);
      } else {
        _error = '数据格式异常';
      }
    } on ApiException catch (exception) {
      _error = exception.isUnauthorized ? '登录已过期' : exception.message;
      if (exception.isUnauthorized) {
        unawaited(Session.instance.refreshMe(silent: true));
      }
    } finally {
      watch.stop();
      _latencyMs = watch.elapsedMilliseconds;
      _fetchedAt = DateTime.now();
      _loading = false;
      if (!_disposed) {
        notifyListeners();
      }
    }
  }

  void _recordHistory(LiveSnapshot snapshot) {
    void push(String key, double? value) {
      if (value == null || value.isNaN) {
        return;
      }
      final List<double> list = _history.putIfAbsent(key, () => <double>[]);
      list.add(value);
      if (list.length > 24) {
        list.removeAt(0);
      }
    }

    push('temperature', snapshot.temperature);
    push('humidity', snapshot.humidity);
    push('pressure', snapshot.pressure);
    push('vibration', snapshot.vibration);
  }

  Future<void> handleAlert(int alertId) async {
    await ApiClient.instance.post('/api/alerts/$alertId/handle');
    await refresh();
  }

  /// 调 Agent 总入口，返回 reply + 协作信息。
  Future<AiReply> askAi(String message) async {
    final dynamic result = await ApiClient.instance.post(
      '/api/agent/chat',
      body: <String, dynamic>{'message': message},
    );
    if (result is! Map) {
      throw ApiException(500, 'AI 响应格式不正确');
    }
    final Map<String, dynamic> json = Map<String, dynamic>.from(result);
    final List<Map<String, dynamic>> agents = <Map<String, dynamic>>[];
    final Object? rawAgents = json['agent_results'];
    if (rawAgents is List) {
      for (final Object? item in rawAgents) {
        if (item is Map) {
          agents.add(Map<String, dynamic>.from(item));
        }
      }
    }
    final List<String> tools = <String>[];
    final Object? rawTools = json['tool_calls'];
    if (rawTools is List) {
      for (final Object? item in rawTools) {
        // 后端 /api/agent/chat 返回 ["query_current_sensor"] 这种字符串数组，
        // 旧版编排器返回 {"tool": "..."}，这里两种都兼容。
        final String name = item is Map
            ? (item['tool'] ?? '').toString()
            : (item ?? '').toString();
        if (name.isNotEmpty && !tools.contains(name)) {
          tools.add(name);
        }
      }
    }
    return AiReply(
      reply: (json['reply'] ?? '暂时没有拿到回答，请稍后再试。').toString(),
      agents: agents,
      tools: tools,
      latencyMs: _asInt(json['latency_ms']),
    );
  }

  void _connectWs() {
    final String? token = Session.instance.token;
    if (token == null || token.isEmpty || !_started) {
      return;
    }
    try {
      final Uri uri = ApiClient.instance
          .wsUri('/ws/sensor', <String, String>{'token': token});
      _channel = WebSocketChannel.connect(uri);
      _wsConnected = true;
      _wsSub = _channel!.stream.listen(
        (dynamic event) {
          _onWsEvent(event);
        },
        onError: (Object error) {
          _wsConnected = false;
          _scheduleReconnect();
        },
        onDone: () {
          _wsConnected = false;
          _scheduleReconnect();
        },
        cancelOnError: true,
      );
    } on Exception {
      _wsConnected = false;
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (!_started) {
      return;
    }
    _retryTimer?.cancel();
    _retryTimer = Timer(const Duration(seconds: 10), _connectWs);
  }

  void _onWsEvent(dynamic event) {
    if (event is! String) {
      return;
    }
    dynamic decoded;
    try {
      decoded = jsonDecode(event);
    } on FormatException {
      return;
    }
    if (decoded is! Map) {
      return;
    }
    final String type = (decoded['type'] ?? '').toString();
    final Object? data = decoded['data'];
    if (type == 'alert') {
      unawaited(refresh());
    } else if (type == 'sensor' && data is Map) {
      unawaited(refresh());
    }
  }

  @override
  void dispose() {
    _disposed = true;
    stop();
    super.dispose();
  }
}

class AiReply {
  AiReply({
    required this.reply,
    required this.agents,
    required this.tools,
    required this.latencyMs,
  });

  final String reply;
  final List<Map<String, dynamic>> agents;
  final List<String> tools;
  final int latencyMs;
}

int _asInt(Object? value) {
  if (value is num) {
    return value.round();
  }
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

int? _asIntNullable(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is num) {
    return value.round();
  }
  return int.tryParse(value.toString());
}

double? _asDouble(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is num) {
    return value.toDouble();
  }
  return double.tryParse(value.toString());
}

String _formatTime(Object? value) {
  final String raw = (value ?? '').toString();
  if (raw.isEmpty) {
    return '';
  }
  final DateTime? parsed = DateTime.tryParse(raw);
  if (parsed == null) {
    return raw;
  }
  final DateTime local = parsed.isUtc ? parsed.toLocal() : parsed;
  final DateTime now = DateTime.now();
  final String hh = local.hour.toString().padLeft(2, '0');
  final String mm = local.minute.toString().padLeft(2, '0');
  if (local.year == now.year &&
      local.month == now.month &&
      local.day == now.day) {
    return '$hh:$mm';
  }
  if (now.difference(local).inDays == 1) {
    return '昨天 $hh:$mm';
  }
  return '${(local.month).toString().padLeft(2, '0')}-${(local.day).toString().padLeft(2, '0')} $hh:$mm';
}
