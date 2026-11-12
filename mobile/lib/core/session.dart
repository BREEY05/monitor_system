import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:pulse_mobile/core/api_client.dart';

/// 登录态 + 服务器地址的单一来源。
///
/// - 启动时从 SharedPreferences 恢复 baseUrl / token / user；
/// - token 存在即视为已登录，随后用 /api/mobile/me 静默校验；
/// - 401 时清空 token 并回到登录页。
class Session extends ChangeNotifier {
  Session._();

  static final Session instance = Session._();

  static const String _kBaseUrl = 'pulse.base_url';
  static const String _kToken = 'pulse.token';
  static const String _kUser = 'pulse.user_json';

  final ApiClient api = ApiClient.instance;

  bool _booting = true;
  bool _loggedIn = false;
  bool _validating = false;
  String _baseUrl = ApiClient.defaultBaseUrl;
  String? _token;
  Map<String, dynamic> _user = <String, dynamic>{};
  Map<String, dynamic> _server = <String, dynamic>{};
  String? _lastError;
  String? _fatalMessage;

  bool get booting => _booting;
  bool get loggedIn => _loggedIn;
  bool get validating => _validating;
  String get baseUrl => _baseUrl;
  String? get token => _token;
  Map<String, dynamic> get user => _user;
  Map<String, dynamic> get server => _server;
  String? get lastError => _lastError;
  String? get fatalMessage => _fatalMessage;

  String get displayName {
    final String name =
        (_user['display_name'] ?? _user['username'] ?? '').toString();
    return name.isEmpty ? '同事' : name;
  }

  String get initial {
    final String name = displayName;
    return name.isEmpty ? 'P' : name.substring(0, 1);
  }

  String get role {
    final String value = (_user['role'] ?? '').toString();
    const Map<String, String> labels = <String, String>{
      'admin': '管理员',
      'operator': '运维',
      'viewer': '只读',
    };
    return labels[value] ?? value;
  }

  String get authProvider {
    final String value = (_user['auth_provider'] ?? '').toString();
    return value == 'feishu' ? '飞书登录' : '账号登录';
  }

  /// App 启动时调用一次。即使 /me 校验失败（离线），也保留 token 进入 App。
  Future<void> bootstrap() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    _baseUrl = ApiClient.normalizeBaseUrl(
        prefs.getString(_kBaseUrl) ?? ApiClient.defaultBaseUrl);
    api.baseUrl = _baseUrl;
    _token = prefs.getString(_kToken);
    final String? userJson = prefs.getString(_kUser);
    if (userJson != null && userJson.isNotEmpty) {
      try {
        final Object? decoded = jsonDecode(userJson);
        if (decoded is Map) {
          _user = Map<String, dynamic>.from(decoded);
        }
      } on FormatException {
        _user = <String, dynamic>{};
      }
    }
    api.token = _token;
    _loggedIn = _token != null && _token!.isNotEmpty;
    _booting = false;
    notifyListeners();
    if (_loggedIn) {
      unawaited(refreshMe(silent: true));
    }
  }

  Future<void> setBaseUrl(String raw) async {
    final String value = ApiClient.normalizeBaseUrl(raw);
    if (value == _baseUrl) {
      return;
    }
    _baseUrl = value;
    api.baseUrl = value;
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kBaseUrl, value);
    notifyListeners();
  }

  Future<void> loginWithPassword(
      {required String username, required String password}) async {
    final dynamic result = await api.post(
      '/api/mobile/login',
      body: <String, dynamic>{'username': username, 'password': password},
      auth: false,
    );
    if (result is! Map) {
      throw ApiException(500, '登录响应格式不正确');
    }
    final Map<String, dynamic> payload = Map<String, dynamic>.from(result);
    final String? newToken = payload['token']?.toString();
    if (newToken == null || newToken.isEmpty) {
      throw ApiException(500, '登录响应缺少 token');
    }
    await _persistLogin(newToken, payload);
  }

  /// 飞书回调拿到 ticket 后由登录页调用。
  Future<void> loginWithToken(
    String newToken, {
    Map<String, dynamic>? user,
    Map<String, dynamic>? server,
  }) async {
    final Map<String, dynamic> payload = <String, dynamic>{
      'token': newToken,
      'user': user ?? <String, dynamic>{},
      if (server != null) 'server': server,
    };
    await _persistLogin(newToken, payload);
  }

  Future<void> _persistLogin(
      String newToken, Map<String, dynamic> payload) async {
    _token = newToken;
    api.token = newToken;
    final Object? server = payload['server'];
    if (server is Map) {
      _server = Map<String, dynamic>.from(server);
    }
    final Object? user = payload['user'];
    if (user is Map) {
      _user = Map<String, dynamic>.from(user);
    }
    _loggedIn = true;
    _lastError = null;
    _fatalMessage = null;
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kToken, newToken);
    await prefs.setString(_kUser, jsonEncode(_user));
    notifyListeners();
    unawaited(refreshMe(silent: true));
  }

  /// 校验 token；401 直接登出，其他错误只记录（离线可用）。
  Future<bool> refreshMe({bool silent = false}) async {
    if (_token == null || _token!.isEmpty) {
      return false;
    }
    _validating = true;
    if (!silent) {
      notifyListeners();
    }
    try {
      final dynamic result = await api.get('/api/mobile/me');
      if (result is Map) {
        final Object? user = result['user'];
        final Object? server = result['server'];
        if (user is Map) {
          _user = Map<String, dynamic>.from(user);
          final SharedPreferences prefs = await SharedPreferences.getInstance();
          await prefs.setString(_kUser, jsonEncode(_user));
        }
        if (server is Map) {
          _server = Map<String, dynamic>.from(server);
        }
      }
      _lastError = null;
      _fatalMessage = null;
      return true;
    } on ApiException catch (error) {
      if (error.isUnauthorized) {
        _fatalMessage = '登录已过期，请重新登录';
        await signOut(keepServer: true, reason: _fatalMessage);
        return false;
      }
      _lastError = error.message;
      return false;
    } finally {
      _validating = false;
      notifyListeners();
    }
  }

  Future<void> signOut({bool keepServer = true, String? reason}) async {
    _token = null;
    api.token = null;
    _loggedIn = false;
    _user = <String, dynamic>{};
    _server = <String, dynamic>{};
    _fatalMessage = reason;
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kToken);
    await prefs.remove(_kUser);
    notifyListeners();
  }

  void clearFatal() {
    _fatalMessage = null;
    notifyListeners();
  }
}
