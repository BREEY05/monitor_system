import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/core/live_data.dart';
import 'package:pulse_mobile/core/session.dart';
import 'package:pulse_mobile/screens/ai_screen.dart';
import 'package:pulse_mobile/screens/alerts_screen.dart';
import 'package:pulse_mobile/screens/devices_screen.dart';
import 'package:pulse_mobile/screens/login_screen.dart';
import 'package:pulse_mobile/screens/overview_screen.dart';
import 'package:pulse_mobile/screens/profile_screen.dart';
import 'package:pulse_mobile/screens/twin_screen.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';
import 'package:pulse_mobile/widgets/pulse_dock.dart';

class PulseApp extends StatelessWidget {
  const PulseApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'PULSE',
      debugShowCheckedModeBanner: false,
      theme: PulseTheme.light(),
      home: const AuthGate(),
    );
  }
}

/// 启动门：booting → 启动页，未登录 → 登录页，已登录 → 主框架。
class AuthGate extends StatelessWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context) {
    final Session session = Session.instance;
    return AnimatedBuilder(
      animation: session,
      builder: (BuildContext context, Widget? child) {
        if (session.booting) {
          return const _SplashScreen();
        }
        if (!session.loggedIn) {
          return const LoginScreen();
        }
        return const RootShell();
      },
    );
  }
}

class _SplashScreen extends StatelessWidget {
  const _SplashScreen();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: PulseColors.bg,
      body: DecoratedBox(
        decoration: const BoxDecoration(gradient: PulseTheme.pageGradient),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Container(
                width: 54,
                height: 54,
                decoration: const BoxDecoration(
                  gradient: PulseTheme.accentGradient,
                  borderRadius: BorderRadius.all(Radius.circular(16)),
                  boxShadow: PulseShadow.avatar,
                ),
                child: const Icon(
                  Icons.graphic_eq_rounded,
                  color: Colors.white,
                  size: 28,
                ),
              ),
              const SizedBox(height: 16),
              const Text('PULSE', style: PulseText.pageTitle),
              const SizedBox(height: 6),
              const Text('正在恢复登录状态…', style: PulseText.meta),
            ],
          ),
        ),
      ),
    );
  }
}

/// 根导航：Scaffold + IndexedStack 4 tab，中央光球 push AI 全屏路由。
class RootShell extends StatefulWidget {
  const RootShell({super.key});

  @override
  State<RootShell> createState() => _RootShellState();
}

class _RootShellState extends State<RootShell> {
  int _index = 0;

  @override
  void initState() {
    super.initState();
    PulseData.instance.start();
  }

  @override
  void dispose() {
    PulseData.instance.stop();
    super.dispose();
  }

  void _select(int index) {
    if (index == _index) {
      return;
    }
    setState(() => _index = index);
  }

  Future<void> _openAi() {
    return Navigator.of(context).push(
      MaterialPageRoute<void>(
          builder: (BuildContext context) => const AiScreen()),
    );
  }

  Future<void> _openTwin() {
    return Navigator.of(context).push(
      MaterialPageRoute<void>(
          builder: (BuildContext context) => const TwinScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: PulseColors.bg,
      body: DecoratedBox(
        decoration: const BoxDecoration(gradient: PulseTheme.pageGradient),
        child: SafeArea(
          bottom: false,
          child: Stack(
            children: <Widget>[
              Positioned.fill(
                child: IndexedStack(
                  index: _index,
                  children: <Widget>[
                    OverviewScreen(
                      onOpenAi: _openAi,
                      onOpenDevices: () => _select(1),
                      onOpenAlerts: () => _select(2),
                      onOpenDevice: _openTwin,
                    ),
                    DevicesScreen(
                      onOpenTwin: _openTwin,
                      onOpenAi: _openAi,
                    ),
                    AlertsScreen(
                      onOpenAi: _openAi,
                      onOpenDevice: _openTwin,
                    ),
                    const ProfileScreen(),
                  ],
                ),
              ),
              Positioned(
                left: 14,
                right: 14,
                bottom: 14,
                child: SafeArea(
                  top: false,
                  child: PulseDock(
                    currentIndex: _index,
                    onTabSelected: _select,
                    onOrbTap: _openAi,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
