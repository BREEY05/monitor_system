import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/core/live_data.dart';
import 'package:pulse_mobile/core/live_view.dart';
import 'package:pulse_mobile/models/alert_item.dart';
import 'package:pulse_mobile/models/metric.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';
import 'package:pulse_mobile/widgets/ai_card.dart';
import 'package:pulse_mobile/widgets/highlight_text.dart';
import 'package:pulse_mobile/widgets/pulse_card.dart';
import 'package:pulse_mobile/widgets/pulse_icon_button.dart';
import 'package:pulse_mobile/widgets/pulse_ring.dart';
import 'package:pulse_mobile/widgets/section_header.dart';
import 'package:pulse_mobile/widgets/stat_tile.dart';
import 'package:pulse_mobile/widgets/status_chip.dart';

/// 01 / 总览：一眼掌握系统脉搏，指标卡 + AI 洞察前置。
/// 数据来自 /api/twin/overview（15s 轮询 + WS 触发），不再用 MockData。
class OverviewScreen extends StatelessWidget {
  const OverviewScreen({
    super.key,
    this.onOpenAi,
    this.onOpenDevices,
    this.onOpenAlerts,
    this.onOpenDevice,
  });

  final VoidCallback? onOpenAi;
  final VoidCallback? onOpenDevices;
  final VoidCallback? onOpenAlerts;
  final VoidCallback? onOpenDevice;

  @override
  Widget build(BuildContext context) {
    final PulseData data = PulseData.instance;
    return AnimatedBuilder(
      animation: data,
      builder: (BuildContext context, Widget? child) {
        final LiveSnapshot? snapshot = data.snapshot;
        final List<Metric> metrics = LiveView.metrics(snapshot);
        final List<AlertItem> alerts = LiveView.alerts(snapshot);
        final int score = snapshot?.healthScore ?? 0;
        return SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(18, 6, 18, 150),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              _GreetingRow(unread: alerts.isEmpty ? 0 : alerts.length),
              const SizedBox(height: 12),
              _StatusChips(snapshot: snapshot, data: data),
              const SizedBox(height: 13),
              _PulseHero(score: score, available: snapshot != null),
              const SizedBox(height: 10),
              _MetricGrid(metrics: metrics, onOpenDevices: onOpenDevices),
              const SizedBox(height: 12),
              AiInsightCard(
                text: LiveView.insightText(snapshot),
                highlights: LiveView.insightHighlights(snapshot),
                actions: LiveView.insightActions(snapshot),
                time: '刚刚',
                onAction: _handleInsightAction,
              ),
              const SizedBox(height: 16),
              SectionHeader(
                title: '最新报警',
                trailing: '全部 ${snapshot?.openAlertTotal ?? 0} 条',
                onTrailingTap: onOpenAlerts,
              ),
              if (alerts.isEmpty)
                PulseCard(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
                  child: SizedBox(
                    width: double.infinity,
                    child: Text(
                      data.loading ? '正在同步实时数据…' : '当前没有未处理报警',
                      style: PulseText.bodySub,
                    ),
                  ),
                )
              else
                _LatestAlert(alert: alerts.first, onTap: onOpenAlerts),
            ],
          ),
        );
      },
    );
  }

  void _handleInsightAction(String action) {
    if (action == '追问 AI') {
      onOpenAi?.call();
    } else if (action == '查看设备') {
      onOpenDevice?.call();
    }
  }
}

class _GreetingRow extends StatelessWidget {
  const _GreetingRow({required this.unread});

  final int unread;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(LiveView.greet(), style: PulseText.hello),
              const SizedBox(height: 4),
              Text(
                LiveView.location(PulseData.instance.snapshot),
                style: PulseText.loc,
              ),
            ],
          ),
        ),
        PulseIconButton(
          icon: Icons.notifications_none_rounded,
          showDot: unread > 0,
        ),
        const SizedBox(width: 8),
        const PulseIconButton(icon: Icons.qr_code_scanner_rounded),
      ],
    );
  }
}

class _StatusChips extends StatelessWidget {
  const _StatusChips({required this.snapshot, required this.data});

  final LiveSnapshot? snapshot;
  final PulseData data;

  @override
  Widget build(BuildContext context) {
    final bool online = snapshot != null && snapshot!.sourceOnline;
    final String onlineLabel = snapshot == null
        ? '连接中'
        : online
            ? '系统在线'
            : '数据源离线';
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      clipBehavior: Clip.none,
      child: Row(
        children: <Widget>[
          StatusChip(
            label: onlineLabel,
            dot: true,
            dotColor: online ? PulseColors.green : PulseColors.amber,
            color: online ? PulseColors.greenInk : PulseColors.amberInk,
            background: online ? PulseColors.greenSoft : PulseColors.amberSoft,
            borderColor: online ? PulseColors.greenLine : PulseColors.amberLine,
          ),
          const SizedBox(width: 6),
          StatusChip(label: LiveView.deviceRatio(snapshot)),
          const SizedBox(width: 6),
          StatusChip(label: LiveView.latency(data)),
        ],
      ),
    );
  }
}

class _PulseHero extends StatelessWidget {
  const _PulseHero({required this.score, required this.available});

  final int score;
  final bool available;

  @override
  Widget build(BuildContext context) {
    return PulseCard(
      radius: PulseRadius.hero,
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      child: SizedBox(
        height: 170,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                const Text('实时脉搏 · 15s 刷新', style: PulseText.label),
                const Spacer(),
                Icon(
                  Icons.sync_rounded,
                  size: 13,
                  color: available ? PulseColors.dim : PulseColors.amber,
                ),
              ],
            ),
            Expanded(
              child: Center(
                child: PulseRing(
                  progress: score / 100,
                  score: available ? score.toString() : '--',
                  caption: '系统健康分',
                  delta: available ? '在线率与报警加权' : '等待实时数据',
                  size: 140,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MetricGrid extends StatelessWidget {
  const _MetricGrid({required this.metrics, this.onOpenDevices});

  final List<Metric> metrics;
  final VoidCallback? onOpenDevices;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: SizedBox(
                height: 88,
                child: StatTile(metric: metrics[0]),
              ),
            ),
            const SizedBox(width: 9),
            Expanded(
              child: SizedBox(
                height: 88,
                child: StatTile(metric: metrics[1]),
              ),
            ),
          ],
        ),
        const SizedBox(height: 9),
        Row(
          children: <Widget>[
            Expanded(
              child: SizedBox(
                height: 88,
                child: StatTile(metric: metrics[2]),
              ),
            ),
            const SizedBox(width: 9),
            Expanded(
              child: SizedBox(
                height: 88,
                child: StatTile(
                  metric: metrics[3],
                  onTap: onOpenDevices,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _LatestAlert extends StatelessWidget {
  const _LatestAlert({required this.alert, this.onTap});

  final AlertItem alert;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final bool critical = alert.level == AlertLevel.critical;
    final Color color = critical ? PulseColors.red : PulseColors.amber;
    final Color background =
        critical ? PulseColors.redSoft : PulseColors.amberSoft;
    final Color border = critical ? PulseColors.redLine : PulseColors.amberLine;
    return PulseCard(
      onTap: onTap,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      child: Row(
        children: <Widget>[
          Container(
            width: 30,
            height: 30,
            decoration: BoxDecoration(
              color: background,
              borderRadius: BorderRadius.circular(9),
              border: Border.all(color: border),
            ),
            child: Icon(Icons.thermostat_rounded, size: 16, color: color),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text.rich(
                  TextSpan(
                    children: <InlineSpan>[
                      TextSpan(
                        text: alert.title,
                        style: PulseText.cardTitle.copyWith(fontSize: 11.5),
                      ),
                      const TextSpan(
                        text: '  ·  ',
                        style: TextStyle(fontSize: 9.5, color: PulseColors.dim),
                      ),
                      TextSpan(
                        text: alert.time,
                        style: PulseText.meta.copyWith(fontSize: 9.5),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 3),
                HighlightedText(
                  alert.subtitle,
                  highlights: alert.highlights,
                  style: PulseText.meta,
                  emphasisStyle: TextStyle(
                    fontSize: 9.5,
                    height: 1.4,
                    fontWeight: FontWeight.w600,
                    color: critical ? PulseColors.redInk : PulseColors.amberInk,
                  ),
                ),
              ],
            ),
          ),
          const Icon(
            Icons.chevron_right_rounded,
            size: 18,
            color: PulseColors.chevron,
          ),
        ],
      ),
    );
  }
}
