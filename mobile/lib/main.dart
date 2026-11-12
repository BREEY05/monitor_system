import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/app.dart';
import 'package:pulse_mobile/core/session.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await Session.instance.bootstrap();
  } catch (error, stack) {
    // 本地存储不可用时也要进入登录页，不能让 App 卡在白屏。
    debugPrint('Session bootstrap failed: $error');
    debugPrintStack(stackTrace: stack);
  }
  runApp(const PulseApp());
}
