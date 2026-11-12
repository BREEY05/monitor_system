import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/core/live_data.dart';
import 'package:pulse_mobile/core/session.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';
import 'package:pulse_mobile/widgets/list_tile_row.dart';
import 'package:pulse_mobile/widgets/pulse_card.dart';
import 'package:pulse_mobile/widgets/pulse_icon_button.dart';
import 'package:pulse_mobile/widgets/pulse_toggle.dart';
import 'package:pulse_mobile/widgets/section_header.dart';

/// 05 / 我的：登录身份、公网服务器状态、配置入口、运维工具与退出登录。
class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  bool _pushEnabled = true;

  void _toast(String feature) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text('$feature · 首期 App 仅做查看 / 报警 / AI，配置仍在网页端'),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 2),
        ),
      );
  }

  Future<void> _confirmSignOut() async {
    final bool? ok = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) => AlertDialog(
        title: const Text('退出登录'),
        content: const Text('退出后需要重新使用飞书扫码登录。'),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('退出'),
          ),
        ],
      ),
    );
    if (ok == true) {
      await Session.instance.signOut();
    }
  }

  @override
  Widget build(BuildContext context) {
    final Session session = Session.instance;
    final PulseData data = PulseData.instance;
    return AnimatedBuilder(
      animation: Listenable.merge(<Listenable>[session, data]),
      builder: (BuildContext context, Widget? child) {
        final LiveSnapshot? snapshot = data.snapshot;
        final String serverName =
            (session.server['name'] ?? 'PULSE 服务').toString();
        final String version = (session.server['version'] ?? '').toString();
        final String thresholdValue = snapshot == null
            ? '--'
            : '${snapshot.thresholdTemperature?.toStringAsFixed(0) ?? '--'}°C / ${snapshot.thresholdHumidity?.toStringAsFixed(0) ?? '--'}%';
        final List<SettingRow> configRows = <SettingRow>[
          SettingRow('阈值与报警策略', thresholdValue, Icons.tune_rounded),
          SettingRow(
            '设备与 3D 模型',
            '${snapshot?.totalCount ?? 0} 台',
            Icons.view_in_ar_rounded,
          ),
          const SettingRow('AI 模型与后端', 'Agent 已连接', Icons.memory_rounded),
          const SettingRow('知识库与 Skill', '网页端管理', Icons.menu_book_rounded),
          const SettingRow('飞书与通知', '已开启', Icons.send_rounded),
          const SettingRow('审计日志', '网页端查看', Icons.receipt_long_rounded),
        ];
        final List<SettingRow> toolRows = <SettingRow>[
          SettingRow(
            '网络与延迟诊断',
            '${data.latencyMs}ms',
            Icons.network_check_rounded,
          ),
          SettingRow(
            '服务健康检查',
            data.wsConnected ? '实时通道正常' : '轮询中',
            Icons.health_and_safety_rounded,
          ),
          const SettingRow('配置回滚', '网页端操作', Icons.history_rounded),
        ];
        return SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(18, 6, 18, 150),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Row(
                children: <Widget>[
                  const Expanded(
                    child: Text('我的', style: PulseText.pageTitle),
                  ),
                  PulseIconButton(
                    icon: Icons.settings_outlined,
                    onTap: () => _toast('设置'),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              PulseCard(
                padding: const EdgeInsets.fromLTRB(13, 13, 12, 13),
                child: Row(
                  children: <Widget>[
                    Container(
                      width: 48,
                      height: 48,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        gradient: PulseTheme.avatarGradient,
                        borderRadius: BorderRadius.circular(14),
                        boxShadow: PulseShadow.avatar,
                      ),
                      child: Text(
                        session.initial,
                        style: const TextStyle(
                          fontSize: 19,
                          fontWeight: FontWeight.w700,
                          color: Colors.white,
                          height: 1.1,
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            session.displayName,
                            style: const TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              color: PulseColors.ink,
                              height: 1.2,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            '${session.role} · ${session.authProvider} · ${serverName.isEmpty ? 'PULSE' : serverName}',
                            style: PulseText.meta,
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
              ),
              const SizedBox(height: 10),
              PulseCard(
                color: data.wsConnected
                    ? PulseColors.greenSoft
                    : PulseColors.amberSoft,
                borderColor: data.wsConnected
                    ? PulseColors.greenLine
                    : PulseColors.amberLine,
                shadows: const <BoxShadow>[],
                padding: const EdgeInsets.fromLTRB(13, 12, 13, 12),
                onTap: () => _toast('服务器详情'),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        Container(
                          width: 6,
                          height: 6,
                          decoration: BoxDecoration(
                            color: data.wsConnected
                                ? PulseColors.green
                                : PulseColors.amber,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          '公网服务器',
                          style: TextStyle(
                            fontSize: 11.5,
                            fontWeight: FontWeight.w700,
                            color: data.wsConnected
                                ? PulseColors.greenInk
                                : PulseColors.amberInk,
                            height: 1.2,
                          ),
                        ),
                        const Spacer(),
                        Text(
                          (data.wsConnected ? '已连接 · ' : '轮询 · ') +
                              (version.isEmpty ? 'TLS' : version),
                          style: TextStyle(
                            fontSize: 9,
                            fontWeight: FontWeight.w600,
                            color: data.wsConnected
                                ? PulseColors.greenInk
                                : PulseColors.amberInk,
                            height: 1.2,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 5),
                    Text(
                      '${session.baseUrl.replaceFirst('https://', '')} · 延迟 ${data.latencyMs}ms · 15s 轮询',
                      style: TextStyle(
                        fontSize: 9.5,
                        color: data.wsConnected
                            ? PulseColors.greenInk
                            : PulseColors.amberInk,
                        height: 1.3,
                        fontFeatures: PulseText.tabular,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 10),
              PulseCard(
                padding: const EdgeInsets.fromLTRB(13, 2, 13, 2),
                child: Column(
                  children: <Widget>[
                    for (int i = 0; i < configRows.length; i++)
                      ListTileRow(
                        icon: configRows[i].icon,
                        title: configRows[i].label,
                        value: configRows[i].value,
                        showDivider: i < configRows.length - 1,
                        onTap: () => _toast(configRows[i].label),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 10),
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
                                ? '严重 / 警告实时推送，提示类聚合'
                                : '已关闭本地提醒，飞书仍会收到严重报警',
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
              const SizedBox(height: 16),
              const SectionHeader(title: '运维工具'),
              PulseCard(
                padding: const EdgeInsets.fromLTRB(13, 2, 13, 2),
                child: Column(
                  children: <Widget>[
                    for (int i = 0; i < toolRows.length; i++)
                      ListTileRow(
                        icon: toolRows[i].icon,
                        title: toolRows[i].label,
                        value: toolRows[i].value,
                        showDivider: i < toolRows.length - 1,
                        onTap: () => _toast(toolRows[i].label),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              SizedBox(
                height: 44,
                child: OutlinedButton(
                  onPressed: _confirmSignOut,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: PulseColors.redInk,
                    side: const BorderSide(color: PulseColors.redLine),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                    ),
                  ),
                  child: const Text(
                    '退出登录',
                    style:
                        TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              const Center(
                child: Text(
                  'PULSE Mobile · M2 · v0.2.0',
                  style: PulseText.labelDim,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// 设置分组内的一行（图标 + 标题 + 右侧值），由 ListTileRow 渲染。
class SettingRow {
  const SettingRow(this.label, this.value, this.icon);

  final String label;
  final String value;
  final IconData icon;
}
