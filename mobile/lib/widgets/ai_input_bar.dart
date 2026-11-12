import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/theme/pulse_theme.dart';

/// AI 对话底部输入栏：附件 / 输入框 / 语音 / 发送。
class AiInputBar extends StatelessWidget {
  const AiInputBar({
    super.key,
    this.onAction,
    this.controller,
    this.onSend,
    this.enabled = true,
    this.busy = false,
    this.hintText = '继续追问，例如：3 号泵组现在状态怎么样？',
  });

  /// 语音、附件等未接入能力的回调。
  final ValueChanged<String>? onAction;
  final TextEditingController? controller;
  final ValueChanged<String>? onSend;
  final bool enabled;
  final bool busy;
  final String hintText;

  void _submit() {
    final String text = controller?.text.trim() ?? '';
    if (text.isEmpty || !enabled) {
      return;
    }
    onSend?.call(text);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 6, 14, 10),
      child: Container(
        height: 54,
        padding: const EdgeInsets.symmetric(horizontal: 6),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.96),
          borderRadius: BorderRadius.circular(27),
          border: Border.all(color: PulseColors.line),
          boxShadow: PulseShadow.iconButton,
        ),
        child: Row(
          children: <Widget>[
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => onAction?.call('更多输入方式'),
              child: Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: PulseColors.card2,
                  shape: BoxShape.circle,
                  border: Border.all(color: PulseColors.line),
                ),
                child: const Icon(
                  Icons.add_rounded,
                  size: 18,
                  color: PulseColors.icon,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: controller,
                enabled: enabled && !busy,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _submit(),
                style: const TextStyle(fontSize: 11.5, color: PulseColors.text),
                decoration: InputDecoration(
                  isCollapsed: true,
                  border: InputBorder.none,
                  hintText: hintText,
                  hintStyle:
                      const TextStyle(fontSize: 10.5, color: PulseColors.dim),
                ),
              ),
            ),
            const SizedBox(width: 6),
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => onAction?.call('语音输入'),
              child: const Padding(
                padding: EdgeInsets.all(6),
                child: Icon(
                  Icons.mic_none_rounded,
                  size: 19,
                  color: PulseColors.sub,
                ),
              ),
            ),
            const SizedBox(width: 4),
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: busy ? null : _submit,
              child: Container(
                width: 38,
                height: 38,
                decoration: const BoxDecoration(
                  color: PulseColors.ink,
                  shape: BoxShape.circle,
                ),
                child: busy
                    ? const Padding(
                        padding: EdgeInsets.all(11),
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(
                        Icons.arrow_upward_rounded,
                        size: 18,
                        color: Colors.white,
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
