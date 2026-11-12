import 'package:material_ui/material_ui.dart';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:pulse_mobile/core/api_client.dart';
import 'package:pulse_mobile/core/session.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';
import 'package:pulse_mobile/widgets/pulse_card.dart';
import 'package:pulse_mobile/widgets/pulse_icon_button.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// 06 / 数字孪生：WebView 承载 /mobile/twin（Three.js + GLB 真实模型）。
///
/// - token 通过 query 传入，页面内所有接口都带 Bearer；
/// - 页面返回按钮通过 FlutterBridge 通道回调 twin:back；
/// - Flutter Web 预览没有 WebView 实现，降级为说明卡。
class TwinScreen extends StatefulWidget {
  const TwinScreen({super.key});

  @override
  State<TwinScreen> createState() => _TwinScreenState();
}

class _TwinScreenState extends State<TwinScreen> {
  WebViewController? _controller;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (kIsWeb) {
      _loading = false;
      return;
    }
    _boot();
  }

  void _boot() {
    final String? token = Session.instance.token;
    if (token == null || token.isEmpty) {
      setState(() {
        _loading = false;
        _error = '登录已过期，请重新登录';
      });
      return;
    }
    final String url =
        '${ApiClient.instance.baseUrl}/mobile/twin?token=${Uri.encodeComponent(token)}';
    final WebViewController controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFFF4F5F7))
      ..addJavaScriptChannel(
        'FlutterBridge',
        onMessageReceived: (JavaScriptMessage message) {
          if (message.message == 'twin:back' && mounted) {
            Navigator.of(context).maybePop();
          }
        },
      )
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageFinished: (String _) {
            if (mounted) {
              setState(() => _loading = false);
            }
          },
          onWebResourceError: (WebResourceError error) {
            if (!mounted || error.isForMainFrame == false) {
              return;
            }
            setState(() {
              _loading = false;
              _error = error.description;
            });
          },
        ),
      )
      ..loadRequest(Uri.parse(url));
    setState(() => _controller = controller);
  }

  void _reload() {
    if (_controller == null) {
      _boot();
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    _controller!.reload();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: PulseColors.bg,
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 6, 14, 6),
              child: Row(
                children: <Widget>[
                  PulseIconButton(
                    icon: Icons.arrow_back_ios_new_rounded,
                    iconSize: 15,
                    onTap: () => Navigator.of(context).maybePop(),
                  ),
                  const Expanded(
                    child: Column(
                      children: <Widget>[
                        Text(
                          '数字孪生',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: PulseColors.ink,
                            height: 1.2,
                          ),
                        ),
                        SizedBox(height: 3),
                        Text('车间 3D 场景 · 实时指标', style: PulseText.labelDim),
                      ],
                    ),
                  ),
                  PulseIconButton(
                    icon: Icons.refresh_rounded,
                    onTap: _reload,
                  ),
                ],
              ),
            ),
            Expanded(child: _body()),
          ],
        ),
      ),
    );
  }

  Widget _body() {
    if (kIsWeb) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(22),
          child: PulseCard(
            padding: const EdgeInsets.all(18),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        color: PulseColors.accentSoft,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Icon(
                        Icons.view_in_ar_rounded,
                        size: 17,
                        color: PulseColors.accent,
                      ),
                    ),
                    const SizedBox(width: 10),
                    const Text('数字孪生需要 Android 环境', style: PulseText.cardTitle),
                  ],
                ),
                const SizedBox(height: 10),
                const Text(
                  '孪生页面由 WebView 承载 Three.js 场景，Flutter Web 预览不支持 WebView。'
                  '安装 APK 后，从设备页或地图卡进入即可旋转、缩放并点击设备查看实时数据。',
                  style: PulseText.bodySub,
                ),
              ],
            ),
          ),
        ),
      );
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(22),
          child: Text(
            '孪生页面加载失败：${_error!}',
            style: PulseText.bodySub.copyWith(color: PulseColors.redInk),
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    final WebViewController? controller = _controller;
    if (controller == null) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2));
    }
    return Stack(
      children: <Widget>[
        Positioned.fill(child: WebViewWidget(controller: controller)),
        if (_loading)
          const Positioned.fill(
            child: ColoredBox(
              color: Color(0xFFF4F5F7),
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    CircularProgressIndicator(strokeWidth: 2),
                    SizedBox(height: 12),
                    Text('正在加载 3D 场景与模型…', style: PulseText.meta),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }
}
