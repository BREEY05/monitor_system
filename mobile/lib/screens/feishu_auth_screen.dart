import 'dart:async';

import 'package:material_ui/material_ui.dart';
import 'package:webview_flutter/webview_flutter.dart';

import 'package:pulse_mobile/core/api_client.dart';
import 'package:pulse_mobile/core/session.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 飞书网页授权：App 内打开 authorize_url，回调页出现后开始 poll。
class FeishuAuthScreen extends StatefulWidget {
  const FeishuAuthScreen({
    super.key,
    required this.authorizeUrl,
    required this.state,
  });

  final String authorizeUrl;
  final String state;

  @override
  State<FeishuAuthScreen> createState() => _FeishuAuthScreenState();
}

class _FeishuAuthScreenState extends State<FeishuAuthScreen> {
  late final WebViewController _controller;
  Timer? _timer;
  bool _polling = false;
  bool _finished = false;
  String? _error;
  bool _pageLoading = true;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(PulseColors.bg)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (String url) {
            if (mounted) {
              setState(() => _pageLoading = true);
            }
            if (url.contains('/api/mobile/feishu/callback')) {
              _startPolling();
            }
          },
          onPageFinished: (String url) {
            if (mounted) {
              setState(() => _pageLoading = false);
            }
          },
          onWebResourceError: (WebResourceError error) {
            if (error.isForMainFrame != true) {
              return;
            }
            if (mounted) {
              setState(() {
                _pageLoading = false;
                _error = '授权页加载失败（${error.description}）';
              });
            }
          },
        ),
      )
      ..loadRequest(Uri.parse(widget.authorizeUrl));
    _timer = Timer(const Duration(seconds: 8), () {
      if (!_finished) {
        _startPolling();
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _startPolling() {
    if (_polling || _finished) {
      return;
    }
    _polling = true;
    _poll();
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 2), (_) => _poll());
  }

  Future<void> _poll() async {
    if (_finished) {
      return;
    }
    try {
      final dynamic result = await ApiClient.instance.post(
        '/api/mobile/feishu/poll',
        body: <String, dynamic>{'state': widget.state},
        auth: false,
      );
      if (result is! Map) {
        return;
      }
      final String status = (result['status'] ?? '').toString();
      if (status == 'ready') {
        _finished = true;
        _timer?.cancel();
        final String token = (result['token'] ?? '').toString();
        final Object? user = result['user'];
        final Object? server = result['server'];
        await Session.instance.loginWithToken(
          token,
          user: user is Map ? Map<String, dynamic>.from(user) : null,
          server: server is Map ? Map<String, dynamic>.from(server) : null,
        );
        if (mounted) {
          Navigator.of(context).pop(true);
        }
      } else if (status == 'denied') {
        _finished = true;
        _timer?.cancel();
        if (mounted) {
          setState(
              () => _error = (result['message'] ?? '未在飞书允许名单内').toString());
        }
      } else if (status == 'expired' || status == 'error') {
        _finished = true;
        _timer?.cancel();
        if (mounted) {
          setState(
              () => _error = (result['message'] ?? '登录已失效，请重试').toString());
        }
      }
    } on ApiException catch (exception) {
      if (exception.isUnauthorized) {
        return;
      }
    } finally {
      if (mounted) {
        setState(() => _pageLoading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: PulseColors.bg,
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 6, 12, 8),
              child: Row(
                children: <Widget>[
                  IconButton(
                    onPressed: () => Navigator.of(context).maybePop(false),
                    icon:
                        const Icon(Icons.close_rounded, color: PulseColors.ink),
                  ),
                  const Expanded(
                    child: Column(
                      children: <Widget>[
                        Text('飞书授权',
                            style: TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                                color: PulseColors.ink)),
                        SizedBox(height: 2),
                        Text('在飞书中确认身份后自动返回', style: PulseText.meta),
                      ],
                    ),
                  ),
                  const SizedBox(width: 44),
                ],
              ),
            ),
            if (_error != null)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                decoration: BoxDecoration(
                  color: PulseColors.redSoft,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: PulseColors.redLine),
                ),
                child: Text(_error!,
                    style: const TextStyle(
                        fontSize: 11, height: 1.5, color: PulseColors.redInk)),
              ),
            if (_pageLoading)
              const LinearProgressIndicator(
                minHeight: 2,
                color: PulseColors.accent,
                backgroundColor: PulseColors.line,
              ),
            Expanded(
              child: WebViewWidget(controller: _controller),
            ),
          ],
        ),
      ),
    );
  }
}
