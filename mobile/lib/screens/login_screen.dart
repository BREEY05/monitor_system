import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/core/api_client.dart';
import 'package:pulse_mobile/core/session.dart';
import 'package:pulse_mobile/screens/feishu_auth_screen.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 登录页：公网服务器地址 + 飞书授权 + 管理员账号兜底。
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final Session _session = Session.instance;
  final TextEditingController _serverController =
      TextEditingController(text: Session.instance.baseUrl);
  final TextEditingController _usernameController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();

  bool _busy = false;
  bool _showPasswordLogin = false;
  String? _message;
  bool _messageIsError = false;
  String? _serverName;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance
        .addPostFrameCallback((_) => _probeServer(silent: true));
  }

  @override
  void dispose() {
    _serverController.dispose();
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  void _setMessage(String text, {bool isError = true}) {
    if (!mounted) {
      return;
    }
    setState(() {
      _message = text;
      _messageIsError = isError;
    });
  }

  Future<void> _probeServer({bool silent = false}) async {
    final String value = _serverController.text;
    final String normalized = ApiClient.normalizeBaseUrl(value);
    if (normalized != _serverController.text.trim()) {
      _serverController.text = normalized;
    }
    try {
      await _session.setBaseUrl(normalized);
      final dynamic result =
          await ApiClient.instance.get('/api/mobile/ping', auth: false);
      if (!mounted) {
        return;
      }
      final Object? server = result is Map ? result['server'] : null;
      final String name =
          server is Map ? (server['name'] ?? '').toString() : '';
      setState(() {
        _serverName = name.isEmpty ? 'PULSE 服务已连接' : name;
      });
      if (!silent) {
        _setMessage('服务器可达 · ${_serverName!}', isError: false);
      }
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _serverName = null;
      });
      if (!silent) {
        _setMessage(error.message, isError: true);
      }
    }
  }

  Future<void> _loginWithFeishu() async {
    if (_busy) {
      return;
    }
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      await _session.setBaseUrl(_serverController.text);
      final dynamic result =
          await ApiClient.instance.get('/api/mobile/feishu/start', auth: false);
      if (result is! Map || result['authorize_url'] == null) {
        throw ApiException(500, '服务端未启用飞书登录');
      }
      final String authorizeUrl = result['authorize_url'].toString();
      final String state = (result['state'] ?? '').toString();
      if (!mounted) {
        return;
      }
      final bool? ok = await Navigator.of(context).push<bool>(
        MaterialPageRoute<bool>(
          fullscreenDialog: true,
          builder: (BuildContext context) => FeishuAuthScreen(
            authorizeUrl: authorizeUrl,
            state: state,
          ),
        ),
      );
      if (ok == true && mounted) {
        _setMessage('登录成功', isError: false);
      }
    } on ApiException catch (error) {
      _setMessage(error.message, isError: true);
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _loginWithPassword() async {
    if (_busy) {
      return;
    }
    final String username = _usernameController.text.trim();
    final String password = _passwordController.text;
    if (username.isEmpty || password.isEmpty) {
      _setMessage('请输入用户名与密码', isError: true);
      return;
    }
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      await _session.setBaseUrl(_serverController.text);
      await _session.loginWithPassword(username: username, password: password);
      if (!mounted) {
        return;
      }
      _setMessage('登录成功', isError: false);
    } on ApiException catch (error) {
      _setMessage(error.message, isError: true);
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: PulseColors.bg,
      body: DecoratedBox(
        decoration: const BoxDecoration(gradient: PulseTheme.pageGradient),
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(22, 40, 22, 28),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                _brand(),
                const SizedBox(height: 30),
                _serverCard(),
                const SizedBox(height: 14),
                _feishuButton(),
                const SizedBox(height: 12),
                _passwordSection(),
                if (_message != null) ...<Widget>[
                  const SizedBox(height: 16),
                  _messageBox(),
                ],
                const SizedBox(height: 26),
                _footer(),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _brand() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Container(
          width: 54,
          height: 54,
          decoration: const BoxDecoration(
            gradient: PulseTheme.accentGradient,
            borderRadius: BorderRadius.all(Radius.circular(16)),
            boxShadow: PulseShadow.avatar,
          ),
          child: const Icon(Icons.graphic_eq_rounded,
              color: Colors.white, size: 28),
        ),
        const SizedBox(height: 18),
        const Text('PULSE',
            style: TextStyle(
                fontSize: 30,
                fontWeight: FontWeight.w800,
                height: 1.1,
                letterSpacing: 1.2,
                color: PulseColors.ink)),
        const SizedBox(height: 6),
        const Text('工业监控 · 移动端', style: PulseText.bodySub),
        const SizedBox(height: 2),
        const Text('远程查看 · 报警 · AI 诊断', style: PulseText.meta),
      ],
    );
  }

  Widget _serverCard() {
    return PulseCardShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text('服务器', style: PulseText.label),
          const SizedBox(height: 8),
          TextField(
            controller: _serverController,
            keyboardType: TextInputType.url,
            style: const TextStyle(fontSize: 13, color: PulseColors.text),
            decoration: _fieldDecoration(
                hint: 'https://pulse.ainavi.online',
                icon: Icons.public_rounded),
            onSubmitted: (_) => _probeServer(),
          ),
          const SizedBox(height: 8),
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  _serverName ?? '公网 HTTPS 或局域网 IP:8000 均可',
                  style: PulseText.meta,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              TextButton(
                onPressed: _busy ? null : () => _probeServer(),
                style: TextButton.styleFrom(
                  foregroundColor: PulseColors.accent,
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  minimumSize: const Size(0, 30),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: const Text('连接测试',
                    style:
                        TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _feishuButton() {
    return SizedBox(
      height: 48,
      width: double.infinity,
      child: FilledButton(
        onPressed: _busy ? null : _loginWithFeishu,
        style: FilledButton.styleFrom(
          backgroundColor: PulseColors.ink,
          foregroundColor: Colors.white,
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        ),
        child: _busy
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: Colors.white),
              )
            : const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: <Widget>[
                  Icon(Icons.qr_code_2_rounded, size: 18),
                  SizedBox(width: 8),
                  Text('使用飞书登录',
                      style: TextStyle(
                          fontSize: 13.5, fontWeight: FontWeight.w700)),
                ],
              ),
      ),
    );
  }

  Widget _passwordSection() {
    return PulseCardShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          InkWell(
            onTap: () =>
                setState(() => _showPasswordLogin = !_showPasswordLogin),
            child: Row(
              children: <Widget>[
                const Expanded(
                  child: Text('管理员账号登录',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: PulseColors.sub)),
                ),
                Icon(
                  _showPasswordLogin
                      ? Icons.expand_less_rounded
                      : Icons.expand_more_rounded,
                  size: 18,
                  color: PulseColors.dim,
                ),
              ],
            ),
          ),
          if (_showPasswordLogin) ...<Widget>[
            const SizedBox(height: 10),
            TextField(
              controller: _usernameController,
              style: const TextStyle(fontSize: 13, color: PulseColors.text),
              decoration: _fieldDecoration(
                  hint: '用户名', icon: Icons.person_outline_rounded),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _passwordController,
              obscureText: true,
              style: const TextStyle(fontSize: 13, color: PulseColors.text),
              decoration: _fieldDecoration(
                  hint: '密码', icon: Icons.lock_outline_rounded),
              onSubmitted: (_) => _loginWithPassword(),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              height: 40,
              child: OutlinedButton(
                onPressed: _busy ? null : _loginWithPassword,
                style: OutlinedButton.styleFrom(
                  foregroundColor: PulseColors.ink,
                  side: const BorderSide(color: PulseColors.line),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12)),
                ),
                child: const Text('登录',
                    style:
                        TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _messageBox() {
    final Color color = _messageIsError ? PulseColors.red : PulseColors.green;
    final Color background =
        _messageIsError ? PulseColors.redSoft : PulseColors.greenSoft;
    final Color border =
        _messageIsError ? PulseColors.redLine : PulseColors.greenLine;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: border),
      ),
      child: Text(
        _message!,
        style: TextStyle(fontSize: 11.5, height: 1.5, color: color),
      ),
    );
  }

  Widget _footer() {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          '网页端仅在厂区内网使用；手机端通过公网服务器远程访问。',
          style: PulseText.meta,
        ),
        SizedBox(height: 4),
        Text('PULSE Mobile · M2', style: PulseText.meta),
      ],
    );
  }

  InputDecoration _fieldDecoration(
      {required String hint, required IconData icon}) {
    return InputDecoration(
      hintText: hint,
      hintStyle: const TextStyle(fontSize: 12, color: PulseColors.dim),
      prefixIcon: Icon(icon, size: 18, color: PulseColors.dim),
      prefixIconConstraints: const BoxConstraints(minWidth: 40),
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
      filled: true,
      fillColor: PulseColors.card2,
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: PulseColors.line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: PulseColors.accent),
      ),
    );
  }
}

/// 登录页用的一张白卡（与首页卡片同视觉）。
class PulseCardShell extends StatelessWidget {
  const PulseCardShell({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      decoration: const BoxDecoration(
        color: PulseColors.card,
        borderRadius: BorderRadius.all(Radius.circular(PulseRadius.card)),
        border: Border.fromBorderSide(BorderSide(color: PulseColors.line)),
        boxShadow: PulseShadow.card,
      ),
      child: child,
    );
  }
}
