import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/core/live_data.dart';
import 'package:pulse_mobile/screens/twin_screen.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';
import 'package:pulse_mobile/widgets/ai_input_bar.dart';
import 'package:pulse_mobile/widgets/pulse_card.dart';
import 'package:pulse_mobile/widgets/pulse_icon_button.dart';
import 'package:pulse_mobile/widgets/reply_text.dart';

/// 02 / AI 对话：真实调用 /api/agent/chat，展示多 Agent 协作与工具轨迹。
class AiScreen extends StatefulWidget {
  const AiScreen({super.key});

  @override
  State<AiScreen> createState() => _AiScreenState();
}

class _AiScreenState extends State<AiScreen> {
  static const List<String> _suggestions = <String>[
    '当前车间有什么风险？',
    '3 号泵组振动是否正常？',
    '生成今日巡检建议',
  ];

  final TextEditingController _controller = TextEditingController();
  final ScrollController _scroll = ScrollController();
  final List<_ChatEntry> _entries = <_ChatEntry>[];
  bool _busy = false;

  @override
  void dispose() {
    _controller.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send(String text) async {
    final String message = text.trim();
    if (message.isEmpty || _busy) {
      return;
    }
    _controller.clear();
    setState(() {
      _busy = true;
      _entries.add(_ChatEntry.user(message));
    });
    _scrollToEnd();
    try {
      final AiReply reply = await PulseData.instance.askAi(message);
      if (!mounted) {
        return;
      }
      setState(() => _entries.add(_ChatEntry.reply(reply)));
    } on Exception catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _entries.add(_ChatEntry.error(error.toString())));
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        _scrollToEnd();
      }
    }
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) {
        return;
      }
      _scroll.animateTo(
        _scroll.position.maxScrollExtent + 120,
        duration: const Duration(milliseconds: 240),
        curve: Curves.easeOut,
      );
    });
  }

  void _openTwin() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const TwinScreen()),
    );
  }

  void _toast(String feature) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('$feature将在后续版本开放')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final PulseData data = PulseData.instance;
    return Scaffold(
      backgroundColor: PulseColors.bg,
      body: DecoratedBox(
        decoration: const BoxDecoration(gradient: PulseTheme.pageGradient),
        child: SafeArea(
          child: Column(
            children: <Widget>[
              _AiHeader(onSettings: () => _toast('AI 设置')),
              _ContextRow(snapshot: data.snapshot, data: data),
              Expanded(
                child: ListView(
                  controller: _scroll,
                  padding: const EdgeInsets.fromLTRB(18, 4, 18, 16),
                  children: <Widget>[
                    if (_entries.isEmpty)
                      _EmptyState(
                        suggestions: _suggestions,
                        onSuggestion: _send,
                      ),
                    for (final _ChatEntry entry in _entries) ...<Widget>[
                      _EntryView(
                        entry: entry,
                        onOpenTwin: _openTwin,
                        onToast: _toast,
                        onQuickAsk: _send,
                      ),
                      const SizedBox(height: 12),
                    ],
                    if (_busy)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 8),
                        child: Row(
                          children: <Widget>[
                            SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            ),
                            SizedBox(width: 8),
                            Text('Orchestrator 正在协调 Agent…',
                                style: PulseText.meta),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
              AiInputBar(
                controller: _controller,
                busy: _busy,
                onSend: _send,
                onAction: (String feature) => _toast(feature),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ChatEntry {
  _ChatEntry.user(this.text)
      : reply = null,
        error = null;
  _ChatEntry.reply(this.reply)
      : text = null,
        error = null;
  _ChatEntry.error(this.error)
      : text = null,
        reply = null;

  final String? text;
  final AiReply? reply;
  final String? error;
}

class _EntryView extends StatelessWidget {
  const _EntryView({
    required this.entry,
    required this.onOpenTwin,
    required this.onToast,
    required this.onQuickAsk,
  });

  final _ChatEntry entry;
  final VoidCallback onOpenTwin;
  final ValueChanged<String> onToast;
  final ValueChanged<String> onQuickAsk;

  @override
  Widget build(BuildContext context) {
    if (entry.text != null) {
      return _UserBubble(text: entry.text!);
    }
    if (entry.error != null) {
      return PulseCard(
        padding: const EdgeInsets.all(12),
        borderColor: PulseColors.redLine,
        child: Row(
          children: <Widget>[
            const Icon(Icons.error_outline_rounded,
                size: 16, color: PulseColors.red),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                '请求失败：${entry.error!}',
                style: PulseText.bodySub.copyWith(color: PulseColors.redInk),
              ),
            ),
          ],
        ),
      );
    }
    final AiReply reply = entry.reply!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        _OrchestratorMeta(reply: reply),
        const SizedBox(height: 9),
        PulseCard(
          padding: const EdgeInsets.fromLTRB(14, 13, 14, 13),
          child: SizedBox(
            width: double.infinity,
            child: ReplyText(text: reply.reply),
          ),
        ),
        if (reply.tools.isNotEmpty) ...<Widget>[
          const SizedBox(height: 10),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: reply.tools
                .map(
                  (String tool) => Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: PulseColors.greenSoft,
                      borderRadius: BorderRadius.circular(PulseRadius.chip),
                      border: Border.all(color: PulseColors.greenLine),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        const Icon(
                          Icons.check_rounded,
                          size: 10,
                          color: PulseColors.green,
                        ),
                        const SizedBox(width: 3),
                        Text(
                          tool,
                          style: PulseText.meta.copyWith(
                            fontSize: 9,
                            fontWeight: FontWeight.w600,
                            color: PulseColors.greenInk,
                          ),
                        ),
                      ],
                    ),
                  ),
                )
                .toList(),
          ),
        ],
        const SizedBox(height: 10),
        Wrap(
          spacing: 7,
          runSpacing: 7,
          children: <Widget>[
            _QuickAction(label: '查看数字孪生', onTap: onOpenTwin),
            _QuickAction(label: '报警时间线', onTap: () => onQuickAsk('列出当前未处理报警')),
            _QuickAction(label: '生成巡检报告', onTap: () => onQuickAsk('生成今日巡检报告')),
          ],
        ),
      ],
    );
  }
}

class _AiHeader extends StatelessWidget {
  const _AiHeader({required this.onSettings});

  final VoidCallback onSettings;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 6, 14, 8),
      child: Row(
        children: <Widget>[
          PulseIconButton(
            icon: Icons.close_rounded,
            onTap: () => Navigator.of(context).maybePop(),
          ),
          Expanded(
            child: Column(
              children: <Widget>[
                Text(
                  'AI 助手',
                  style: PulseText.cardTitle.copyWith(fontSize: 15),
                ),
                const SizedBox(height: 3),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: <Widget>[
                    Container(
                      width: 5,
                      height: 5,
                      decoration: const BoxDecoration(
                        color: PulseColors.green,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 4),
                    Text(
                      'PULSE · 在线',
                      style: PulseText.meta.copyWith(fontSize: 9.5),
                    ),
                  ],
                ),
              ],
            ),
          ),
          PulseIconButton(
            icon: Icons.tune_rounded,
            onTap: onSettings,
          ),
        ],
      ),
    );
  }
}

class _ContextRow extends StatelessWidget {
  const _ContextRow({required this.snapshot, required this.data});

  final LiveSnapshot? snapshot;
  final PulseData data;

  @override
  Widget build(BuildContext context) {
    final List<String> chips = <String>[
      snapshot == null
          ? '等待实时数据'
          : ('${snapshot!.onlineCount}/${snapshot!.totalCount} 台在线'),
      '实时数据已注入',
      '未处理报警 ${snapshot?.openAlertTotal ?? 0}',
    ];
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(18, 2, 18, 10),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: PulseColors.line2)),
      ),
      child: Row(
        children: <Widget>[
          const Text('上下文', style: PulseText.labelDim),
          const SizedBox(width: 9),
          Expanded(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              clipBehavior: Clip.none,
              child: Row(
                children: <Widget>[
                  for (int i = 0; i < chips.length; i++) ...<Widget>[
                    if (i > 0) const SizedBox(width: 6),
                    _ContextChip(label: chips[i]),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ContextChip extends StatelessWidget {
  const _ContextChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: PulseColors.accentSoft,
        borderRadius: BorderRadius.circular(PulseRadius.chip),
        border: Border.all(color: PulseColors.accentLine),
      ),
      child: Text(
        label,
        style: PulseText.meta.copyWith(
          fontSize: 9,
          fontWeight: FontWeight.w600,
          color: PulseColors.accentInk,
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.suggestions, required this.onSuggestion});

  final List<String> suggestions;
  final ValueChanged<String> onSuggestion;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                width: 26,
                height: 26,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: PulseTheme.accentGradient,
                ),
                child: const Icon(
                  Icons.auto_awesome_rounded,
                  size: 13,
                  color: Colors.white,
                ),
              ),
              const SizedBox(width: 9),
              Text(
                'PULSE 助手',
                style: PulseText.cardTitle.copyWith(fontSize: 12),
              ),
            ],
          ),
          const SizedBox(height: 10),
          PulseCard(
            padding: const EdgeInsets.fromLTRB(14, 13, 14, 13),
            child: Text(
              '你好，我可以读取车间实时数据、历史趋势与维护知识库。'
              '直接问设备状态、报警原因或巡检建议，我会给出带数据依据的结论。',
              style: PulseText.body.copyWith(fontSize: 12, height: 1.7),
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 7,
            runSpacing: 7,
            children: suggestions
                .map(
                  (String text) => GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: () => onSuggestion(text),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 11,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: PulseColors.card,
                        borderRadius: BorderRadius.circular(PulseRadius.chip),
                        border: Border.all(color: PulseColors.line),
                      ),
                      child: Text(
                        text,
                        style: PulseText.chip.copyWith(
                          fontSize: 10,
                          color: PulseColors.text,
                        ),
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
        ],
      ),
    );
  }
}

class _UserBubble extends StatelessWidget {
  const _UserBubble({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 280),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: const BoxDecoration(
          color: PulseColors.ink,
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(18),
            topRight: Radius.circular(18),
            bottomLeft: Radius.circular(18),
            bottomRight: Radius.circular(5),
          ),
        ),
        child: Text(
          text,
          style:
              const TextStyle(fontSize: 12, height: 1.5, color: Colors.white),
        ),
      ),
    );
  }
}

class _OrchestratorMeta extends StatelessWidget {
  const _OrchestratorMeta({required this.reply});

  final AiReply reply;

  @override
  Widget build(BuildContext context) {
    final int agentCount = reply.agents.isEmpty ? 1 : reply.agents.length;
    final String meta =
        '$agentCount 个 Agent 协作 · ${(reply.latencyMs / 1000).toStringAsFixed(1)}s';
    return Row(
      children: <Widget>[
        Container(
          width: 24,
          height: 24,
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            gradient: PulseTheme.accentGradient,
          ),
          child: const Icon(
            Icons.auto_awesome_rounded,
            size: 12,
            color: Colors.white,
          ),
        ),
        const SizedBox(width: 8),
        Text.rich(
          TextSpan(
            children: <InlineSpan>[
              TextSpan(
                text: 'Orchestrator',
                style: PulseText.cardTitle.copyWith(fontSize: 10.5),
              ),
              TextSpan(
                text: '  ·  $meta',
                style: PulseText.meta.copyWith(fontSize: 9.5),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _QuickAction extends StatelessWidget {
  const _QuickAction({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
        decoration: BoxDecoration(
          color: PulseColors.card,
          borderRadius: BorderRadius.circular(PulseRadius.chip),
          border: Border.all(color: PulseColors.line),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Icon(Icons.add_rounded, size: 12, color: PulseColors.accent),
            const SizedBox(width: 4),
            Text(
              label,
              style: PulseText.chip.copyWith(
                fontSize: 10,
                color: PulseColors.text,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
