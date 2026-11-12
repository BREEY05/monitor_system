/// 报警等级：严重 / 警告 / 提示。
enum AlertLevel { critical, warning, info }

/// 报警时间线上的一条记录。
class AlertItem {
  const AlertItem({
    required this.id,
    required this.title,
    required this.level,
    required this.time,
    required this.subtitle,
    this.highlights = const <String>[],
    this.actions = const <String>[],
    this.primaryAction,
  });

  final String id;
  final String title;
  final AlertLevel level;
  final String time;
  final String subtitle;

  /// subtitle 里需要用主文字加粗强调的片段（如 33.2°C）。
  final List<String> highlights;

  /// 卡片底部操作按钮，按顺序展示。
  final List<String> actions;

  /// 哪个操作样式为主按钮（墨黑底）；为 null 时全部为次级按钮。
  final String? primaryAction;
}
