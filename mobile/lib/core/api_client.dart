import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

/// 后端返回的非 2xx 响应统一抛这个异常，UI 只展示 [message]。
class ApiException implements Exception {
  ApiException(this.statusCode, this.message);

  final int statusCode;
  final String message;

  bool get isUnauthorized => statusCode == 401;
  bool get isNetwork => statusCode == 0;

  @override
  String toString() => message;
}

/// PULSE 后端 HTTP 客户端。
///
/// - 使用 package:http，Android 上走 IOClient、Web 预览走 BrowserClient；
/// - baseUrl 可指向公网 https://pulse.ainavi.online，也可指向局域网 http://IP:8000；
/// - token 由 Session 写入，401 由调用方决定是否登出。
class ApiClient {
  ApiClient._();

  static final ApiClient instance = ApiClient._();

  static const String defaultBaseUrl = 'https://pulse.ainavi.online';

  final http.Client _client = http.Client();

  String _baseUrl = defaultBaseUrl;

  String? token;

  String get baseUrl => _baseUrl;

  set baseUrl(String value) {
    _baseUrl = normalizeBaseUrl(value);
  }

  static String normalizeBaseUrl(String raw) {
    String value = raw.trim();
    if (value.isEmpty) {
      return defaultBaseUrl;
    }
    if (!value.startsWith('http://') && !value.startsWith('https://')) {
      value = 'https://$value';
    }
    while (value.length > 8 && value.endsWith('/')) {
      value = value.substring(0, value.length - 1);
    }
    return value;
  }

  Uri uri(String path, [Map<String, String>? query]) {
    final String normalized = path.startsWith('/') ? path : '/$path';
    return Uri.parse(_baseUrl + normalized).replace(
      queryParameters: (query == null || query.isEmpty) ? null : query,
    );
  }

  Uri wsUri(String path, [Map<String, String>? query]) {
    final Uri http = uri(path, query);
    return http.replace(scheme: http.scheme == 'https' ? 'wss' : 'ws');
  }

  /// 发起请求并返回 JSON（Map / List / null）。网络错误抛 statusCode = 0。
  Future<dynamic> request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? query,
    bool auth = true,
    Duration timeout = const Duration(seconds: 25),
  }) async {
    final http.Request request = http.Request(method, uri(path, query));
    request.headers['Accept'] = 'application/json';
    if (body != null) {
      request.headers['Content-Type'] = 'application/json; charset=utf-8';
      request.body = jsonEncode(body);
    }
    if (auth && token != null && token!.isNotEmpty) {
      request.headers['Authorization'] = 'Bearer $token';
    }
    http.StreamedResponse response;
    try {
      response = await _client.send(request).timeout(timeout);
    } on Exception catch (error) {
      throw ApiException(0, '无法连接服务器，请检查网络与地址（$error）');
    }
    final String text = await response.stream.bytesToString().timeout(timeout);
    dynamic decoded;
    if (text.trim().isNotEmpty) {
      try {
        decoded = jsonDecode(text);
      } on FormatException {
        decoded = text;
      }
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      String message = '服务器返回 ${response.statusCode}';
      if (decoded is Map && decoded['detail'] != null) {
        message = decoded['detail'].toString();
      } else if (decoded is Map && decoded['message'] != null) {
        message = decoded['message'].toString();
      } else if (decoded is String && decoded.trim().isNotEmpty) {
        message = decoded.trim();
      }
      throw ApiException(response.statusCode, message);
    }
    return decoded;
  }

  Future<dynamic> get(String path,
      {Map<String, String>? query, bool auth = true}) {
    return request('GET', path, query: query, auth: auth);
  }

  Future<dynamic> post(String path,
      {Map<String, dynamic>? body, bool auth = true}) {
    return request('POST', path, body: body, auth: auth);
  }

  void close() {
    _client.close();
  }
}
