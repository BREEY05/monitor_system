/// 对话角色。M1 只渲染用户提问 + 结构化的 AI 回答卡片。
enum ChatRole { user, assistant }

/// 一条聊天消息（不可变）。
class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.role,
    required this.text,
  });

  final String id;
  final ChatRole role;
  final String text;
}
