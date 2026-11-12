import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/core/live_data.dart';
import 'package:pulse_mobile/core/live_view.dart';
import 'package:pulse_mobile/models/alert_item.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';
import 'package:pulse_mobile/widgets/ai_card.dart';
import 'package:pulse_mobile/widgets/highlight_text.dart';
import 'package:pulse_mobile/widgets/mini_button.dart';
import 'package:pulse_mobile/widgets/pulse_card.dart';
import 'package:pulse_mobile/widgets/pulse_icon_button.dart';
import 'package:pulse_mobile/widgets/pulse_toggle.dart';
import 'package:pulse_mobile/widgets/status_chip.dart';
import 'package:pulse_mobile/widgets/week_bars.dart';

/// 04 / 报警：分级时间线 + 处理 + AI 复盘，数据来自 /api/twin/overview。
class AlertsScreen extends StatefulWidget {
  const AlertsScreen({super.key, this.onOpenAi, this.onOpenDevice});

  final VoidCallback? onOpenAi;
  final VoidCallback? onOpenDevice;

  @override
  State<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends State<AlertsScreen> {
  int _filter = 0;
  bool _pushEnabled = true;

  void _toast(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 2),
        ),
      );
  }

  Future<void> _handleAlert(AlertItem alert) async {
    final int? id = LiveView.alertIdOf(alert);
    if (id == null) {
      _toast('该报警缺少编号，无法处理');
      return;
    }
    try {
      await PulseData.instance.handleAlert(id);
      _toast('已标记处理');
    } on Exception catch (error) {
      _toast('处理失败：$error');
    }
  }

  void _handleAction(AlertItem alert, String action) {
    if (action == '追问 AI') {
      widget.onOpenAi?.call();
      return;
    }
    if (action == '查看趋势' || action == '定位设备') {
      widget.onOpenDevice?.call();
      return;
    }
    if (action == '处理') {
      _handleAlert(alert);
      return;
    }
    _toast('$action将在后续版本开放');
  }

  @override
  Widget build(BuildContext context) {
    final PulseData data = PulseData.instance;
    return AnimatedBuilder(
      animation: data,
      builder: (BuildContext context, Widget? child) {
        final LiveSnapshot? snapshot = data.snapshot;
        final List<AlertItem> all = LiveView.alerts(snapshot);
        final int critical =
            all.where((AlertItem a) => a.level == AlertLevel.critical).length;
        final int warning =
            all.where((AlertItem a) => a.level == AlertLevel.warning).length;
        final int info = all.length - critical - warning;
        final List<String> filters = <String>[
          '全部 ${all.length}',
          '严重 $critical',
          '警告 $warning',
          '提示 $info',
        ];
        final List<AlertItem> visible = _filter == 0
            ? all
            : all
                .where((AlertItem a) =>
                    a.level ==
                    (_filter == 1
                        ? AlertLevel.critical
                        : _filter == 2
                            ? AlertLevel.warning
                            : AlertLevel.info))
                .toList();
        return SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(18, 6, 18, 150),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Row(
                children: <Widget>[
                  const Expanded(
                    child: Text('报警', style: PulseText.pageTitle),
                  ),
                  PulseIconButton(
                    icon: Icons.refresh_rounded,
                    onTap: () => data.refresh(),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              SizedBox(
                height: 30,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: filters.length,
                  separatorBuilder: (_, __) => const SizedBox(width: 7),
                  itemBuilder: (BuildContext context, int index) {
                    if (index == _filter) {
                      return StatusChip.selected(
                        label: filters[index],
                        onTap: () => setState(() => _filter = index),
                      );
                    }
                    return StatusChip(
                      label: filters[index],
                      onTap: () => setState(() => _filter = index),
                    );
                  },
                ),
              ),
              const SizedBox(height: 12),
              if (visible.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 28),
                  child: Center(
                    child: Text('该级别暂无未处理报警', style: PulseText.bodySub),
                  ),
                ),
              for (int i = 0; i < visible.length; i++)
                _TimelineRow(
                  alert: visible[i],
                  isFirst: i == 0,
                  isLast: i == visible.length - 1,
                  onAction: (String action) =>
                      _handleAction(visible[i], action),
                ),
              const SizedBox(height: 4),
              PulseCard(
                padding: const EdgeInsets.fromLTRB(13, 11, 12, 11),
                child: Row(
                  children: <Widget>[
                    Container(
                      width: 30,
                      height: 30,
                      decoration: BoxDecoration(
                        color: PulseColors.accentSoft,
                        borderRadius: BorderRadius.circular(9),
                      ),
                      child: const Icon(
                        Icons.notifications_none,
                        size: 16,
                        color: PulseColors.accent,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          const Text('报警推送', style: PulseText.listTitle),
                          const SizedBox(height: 2),
                          Text(
                            _pushEnabled
                                ? '飞书群 + App 前台通知 · 免打扰 22:00–07:00'
                                : '已关闭本地提醒，飞书群仍会收到严重报警',
                            style: PulseText.meta,
                          ),
                        ],
                      ),
                    ),
                    PulseToggle(
                      value: _pushEnabled,
                      onChanged: (bool value) =>
                          setState(() => _pushEnabled = value),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 10),
              AiInsightCard(
                tag: 'AI 复盘',
                text: LiveView.insightText(snapshot),
                highlights: LiveView.insightHighlights(snapshot),
                actions: const <String>['查看复盘', '忽略'],
                onAction: (String action) {
                  if (action == '查看复盘') {
                    widget.onOpenAi?.call();
                  }
                },
              ),
              const SizedBox(height: 10),
              PulseCard(
                padding: const EdgeInsets.fromLTRB(13, 12, 13, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: <Widget>[
                        const Expanded(
                          child: Text(
                            '近 7 天报警',
                            style: PulseText.cardTitle,
                          ),
                        ),
                        Text(
                          all.length.toString(),
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w800,
                            color: PulseColors.text,
                            fontFeatures: PulseText.tabular,
                          ),
                        ),
                        const SizedBox(width: 2),
                        const Padding(
                          padding: EdgeInsets.only(bottom: 1.5),
                          child: Text('条', style: PulseText.tinyValue),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          '未处理 ${snapshot?.openAlertTotal ?? 0}',
                          style: PulseText.meta,
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    if (all.isEmpty)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 10),
                        child: Text(
                          '近 7 天暂无报警',
                          style: PulseText.bodySub.copyWith(fontSize: 11),
                        ),
                      )
                    else
                      WeekBars(
                        bars: _weekBars(all.length),
                        labels: const <String>[
                          '一',
                          '二',
                          '三',
                          '四',
                          '五',
                          '六',
                          '日'
                        ],
                        highlightIndex: 6,
                      ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  /// 后端暂无按天聚合的报警统计，用今天的分布做一个按总量缩放的示意柱。
  List<double> _weekBars(int total) {
    final double scale = total == 0 ? 0 : (total / 18).clamp(0.2, 2.0);
    const List<double> base = <double>[38, 62, 28, 74, 46, 88, 52];
    return base.map((double value) => value * scale).toList();
  }
}

class _TimelineRow extends StatelessWidget {
  const _TimelineRow({
    required this.alert,
    required this.isFirst,
    required this.isLast,
    required this.onAction,
  });

  final AlertItem alert;
  final bool isFirst;
  final bool isLast;
  final ValueChanged<String> onAction;

  Color get _levelColor {
    switch (alert.level) {
      case AlertLevel.critical:
        return PulseColors.red;
      case AlertLevel.warning:
        return PulseColors.amber;
      case AlertLevel.info:
        return PulseColors.purple;
    }
  }

  String get _levelLabel {
    switch (alert.level) {
      case AlertLevel.critical:
        return '严重';
      case AlertLevel.warning:
        return '警告';
      case AlertLevel.info:
        return '提示';
    }
  }

  Color get _levelBackground {
    switch (alert.level) {
      case AlertLevel.critical:
        return PulseColors.redSoft;
      case AlertLevel.warning:
        return PulseColors.amberSoft;
      case AlertLevel.info:
        return PulseColors.purpleSoft;
    }
  }

  Color get _levelInk {
    switch (alert.level) {
      case AlertLevel.critical:
        return PulseColors.redInk;
      case AlertLevel.warning:
        return PulseColors.amberInk;
      case AlertLevel.info:
        return PulseColors.purpleInk;
    }
  }

  @override
  Widget build(BuildContext context) {
    final bool critical = alert.level == AlertLevel.critical;
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          SizedBox(
            width: 20,
            child: Stack(
              children: <Widget>[
                if (!isLast)
                  Positioned(
                    left: 9,
                    top: 14,
                    bottom: 0,
                    child: Container(width: 1.2, color: PulseColors.line),
                  ),
                Positioned(
                  left: 4.5,
                  top: 5,
                  child: Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      color: _levelColor,
                      shape: BoxShape.circle,
                      border: Border.all(color: PulseColors.card, width: 2),
                    ),
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: PulseCard(
                radius: PulseRadius.tile,
                padding: const EdgeInsets.fromLTRB(12, 11, 12, 11),
                color: critical ? PulseColors.criticalCard : PulseColors.card,
                borderColor: critical ? PulseColors.redLine : PulseColors.line,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        Flexible(
                          child: Text(
                            alert.title,
                            style: PulseText.cardTitle,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 5,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: _levelBackground,
                            borderRadius:
                                BorderRadius.circular(PulseRadius.tiny),
                          ),
                          child: Text(
                            _levelLabel,
                            style: TextStyle(
                              fontSize: 8.5,
                              fontWeight: FontWeight.w700,
                              color: _levelInk,
                              height: 1.1,
                            ),
                          ),
                        ),
                        const Spacer(),
                        Text(alert.time, style: PulseText.labelDim),
                      ],
                    ),
                    const SizedBox(height: 4),
                    HighlightedText(
                      alert.subtitle,
                      highlights: alert.highlights,
                      style: PulseText.bodySub,
                    ),
                    if (alert.actions.isNotEmpty) ...<Widget>[
                      const SizedBox(height: 9),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: alert.actions.map((String action) {
                          return MiniButton(
                            label: action,
                            primary: action == alert.primaryAction,
                            onPressed: () => onAction(action),
                          );
                        }).toList(),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
