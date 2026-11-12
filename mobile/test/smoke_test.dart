import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:pulse_mobile/core/live_data.dart';
import 'package:pulse_mobile/core/live_view.dart';
import 'package:pulse_mobile/models/alert_item.dart';
import 'package:pulse_mobile/models/device.dart';
import 'package:pulse_mobile/models/metric.dart';
import 'package:pulse_mobile/screens/alerts_screen.dart';
import 'package:pulse_mobile/screens/login_screen.dart';
import 'package:pulse_mobile/screens/overview_screen.dart';
import 'package:pulse_mobile/widgets/reply_text.dart';

/// M2 测试：不触网、不起计时器。
/// - 数据层：/api/twin/overview 的 JSON → LiveSnapshot → LiveView 映射
/// - UI 层：未登录时的登录页、未拿到快照时的总览 / 报警空态
void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  Map<String, dynamic> overviewJson() => <String, dynamic>{
        'generated_at': '2026-11-12T09:32:10+08:00',
        'source': <String, dynamic>{
          'label': '网关 A',
          'online': true,
          'stale': false
        },
        'thresholds': <String, dynamic>{
          'temperature': 31,
          'humidity': 60,
          'vibration': 0.5,
        },
        'plant': <String, dynamic>{
          'temperature': 33.2,
          'humidity': 52.1,
          'pressure': 1012,
          'vibration': 0.18,
        },
        'summary': <String, dynamic>{
          'total': 2,
          'online': 1,
          'data_online': true
        },
        'devices': <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'device-1',
            'name': '工业设备 #02',
            'status': '运行中',
            'online': true,
            'station': '工位 01',
            'sensor_bound': true,
            'risk': <String, dynamic>{'level': 'warning'},
            'alerts': <String, dynamic>{'open': 1},
            'model_url': '/static/uploads/device_models/pump_test_bench.glb',
            'index': 1,
          },
          <String, dynamic>{
            'id': 'device-2',
            'name': '六轴机械臂工作站',
            'status': '离线',
            'online': false,
            'station': '工位 02',
            'sensor_bound': false,
          },
        ],
        'alerts': <String, dynamic>{
          'open_total': 2,
          'items': <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 12,
              'title': '温度超限 · 工业设备 #02',
              'level': 'critical',
              'time': '2026-11-12T09:32:00+08:00',
              'source': '温度传感器',
              'device_id': 'device-1',
              'type': 'temperature',
              'value': 33.2,
              'threshold': 31,
            },
            <String, dynamic>{
              'id': 13,
              'title': '振动高于基线',
              'level': 'warning',
              'time': '2026-11-12T08:47:00+08:00',
              'source': '网关 A',
              'device_id': 'device-1',
              'type': 'vibration',
              'value': 0.18,
              'threshold': 0.5,
            },
          ],
        },
      };

  group('数据层：overview → LiveSnapshot → LiveView', () {
    test('解析车间指标、设备、报警与汇总', () {
      final LiveSnapshot snapshot = LiveSnapshot.fromJson(overviewJson());

      expect(snapshot.sourceLabel, '网关 A');
      expect(snapshot.sourceOnline, isTrue);
      expect(snapshot.temperature, 33.2);
      expect(snapshot.thresholdTemperature, 31);
      expect(snapshot.thresholdVibration, 0.5);
      expect(snapshot.devices.length, 2);
      expect(snapshot.devices.first.sensorBound, isTrue);
      expect(snapshot.devices.first.openAlerts, 1);
      expect(snapshot.devices.last.online, isFalse);
      expect(snapshot.alerts.length, 2);
      expect(snapshot.alerts.first.id, 12);
      expect(snapshot.alerts.first.isCritical, isTrue);
      expect(snapshot.alerts.last.isWarning, isTrue);
      expect(snapshot.openAlertTotal, 2);
      expect(snapshot.onlineCount, 1);
      expect(snapshot.totalCount, 2);
      expect(snapshot.dataOnline, isTrue);
    });

    test('健康分按在线率与报警扣分', () {
      final LiveSnapshot snapshot = LiveSnapshot.fromJson(overviewJson());
      // 70 * 1/2 + 30 = 65，未处理 2 条 -7，严重 1 条 -5 → 53
      expect(snapshot.healthScore, 53);
    });

    test('缺失数据不抛异常，指标显示占位', () {
      final LiveSnapshot snapshot = LiveSnapshot.fromJson(<String, dynamic>{});
      expect(snapshot.devices, isEmpty);
      expect(snapshot.alerts, isEmpty);
      expect(snapshot.temperature, isNull);
      expect(snapshot.totalCount, 0);

      final List<Metric> metrics = LiveView.metrics(snapshot);
      expect(metrics.length, 4);
      expect(metrics.first.label, '温度');
      expect(metrics.first.value, '--');
    });

    test('设备与报警映射成 UI 模型', () {
      final LiveSnapshot snapshot = LiveSnapshot.fromJson(overviewJson());
      final List<Device> devices = LiveView.devices(snapshot);
      expect(devices.length, 2);
      expect(devices.first.name, '工业设备 #02');
      expect(devices.first.status, DeviceStatus.running);
      expect(devices.last.status, DeviceStatus.offline);

      final List<AlertItem> alerts = LiveView.alerts(snapshot);
      expect(alerts.length, 2);
      expect(alerts.first.level, AlertLevel.critical);
      expect(alerts.last.level, AlertLevel.warning);
      expect(alerts.first.actions, contains('处理'));
      expect(LiveView.alertIdOf(alerts.first), 12);
    });
  });

  group('UI 层：未登录 / 无快照', () {
    testWidgets('登录页展示服务器地址与飞书登录入口', (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1170, 2532);
      tester.view.devicePixelRatio = 3.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
      await tester.pump();

      expect(find.text('PULSE'), findsOneWidget);
      expect(find.text('使用飞书登录'), findsOneWidget);
      expect(find.text('连接测试'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('总览在无快照时展示空态', (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1170, 2532);
      tester.view.devicePixelRatio = 3.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: OverviewScreen())),
      );
      await tester.pump();

      expect(find.text('实时脉搏 · 15s 刷新'), findsOneWidget);
      expect(find.text('系统健康分'), findsOneWidget);
      expect(find.text('最新报警'), findsOneWidget);
      expect(find.text('当前没有未处理报警'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('报警页在无快照时展示空态', (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1170, 2532);
      tester.view.devicePixelRatio = 3.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: AlertsScreen())),
      );
      await tester.pump();

      expect(find.text('报警'), findsWidgets);
      expect(find.text('该级别暂无未处理报警'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('AI 回复渲染', () {
    testWidgets('Markdown 加粗/列表/标题被解析成富文本', (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1170, 2532);
      tester.view.devicePixelRatio = 3.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: ReplyText(
              text: '**当前传感器数据**\n- 温度: 27.4°C\n### 结论\n数据正常',
            ),
          ),
        ),
      );
      await tester.pump();

      // 标题与加粗标记不应原样显示
      expect(find.textContaining('**', findRichText: true), findsNothing);
      expect(find.textContaining('#', findRichText: true), findsNothing);
      expect(find.textContaining('当前传感器数据', findRichText: true), findsWidgets);
      expect(
          find.textContaining('温度: 27.4°C', findRichText: true), findsWidgets);
      expect(find.textContaining('数据正常', findRichText: true), findsWidgets);
      expect(tester.takeException(), isNull);
    });
  });
}
