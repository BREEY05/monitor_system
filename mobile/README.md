# PULSE Mobile · M1

工业监控系统 PULSE 的移动端（Flutter）M1 里程碑：**六屏高保真静态界面 + 本地 Mock 数据**。
目标是先把信息架构、视觉 token、组件拆分与交互路径跑通，M2 再接真实 API / 三维场景。

参考材料：

- 设计规范：`docs/mobile-app-spec.md` 第 7 / 11 节（API 契约、设计系统、六屏结构、数字孪生）
- 概念稿：`output/mobile-mockups/index.html`（六屏 390 × 844 高保真稿）、`twin-screen.html`
- 逐屏图：`output/mobile-mockups/01-overview.png` … `06-twin.png`
- M0 接口形状：`api_server.py` 中的 `/api/mobile/config-schema`、`/api/twin/scene` 等

## 快速开始

当前仓库里没有 Flutter SDK，也没有生成 `android/` 平台目录（M1 只交付 Dart 源码）。
在已安装 Flutter（3.24+ / Dart 3.5+）的机器上：

```bash
cd mobile

# 生成 android 平台壳（保留 lib/ 与 test/，只补 android/ 等目录）
flutter create --platforms android --project-name pulse_mobile .

flutter pub get
flutter analyze
flutter test
flutter run -d <device>
```

注意：`flutter create` 可能用模板覆盖 `pubspec.yaml` / `analysis_options.yaml`。
如果被覆盖，恢复本仓库里的这两个文件即可（依赖只有 flutter + cupertino_icons + flutter_lints）。
也可以先在空目录 `flutter create --platforms android --project-name pulse_mobile app`，
再把生成的 `android/` 与 `.metadata` 拷到 `mobile/` 下，避免动到已写好的源码。

包名 `pulse_mobile`，所以所有 import 都是 `package:pulse_mobile/...`。

## 目录结构

```
mobile/
├─ pubspec.yaml              # 无三方运行时依赖；无 assets/字体
├─ analysis_options.yaml     # include package:flutter_lints/flutter.yaml
├─ lib/
│  ├─ main.dart              # runApp(const PulseApp())
│  ├─ app.dart               # MaterialApp + RootShell（IndexedStack 4 tab + 固定 dock）
│  ├─ theme/
│  │  └─ pulse_theme.dart    # 颜色 / 圆角 / 阴影 / 文字 + ThemeData(M3)
│  ├─ models/                # 不可变数据类
│  │  ├─ device.dart         # Device, DeviceMetric, DeviceStatus, TwinZone, TwinSpot, TwinState, InspectionTask
│  │  ├─ alert_item.dart     # AlertItem, AlertLevel
│  │  ├─ metric.dart         # Metric, MetricTrend
│  │  └─ chat_message.dart   # ChatMessage, ChatRole
│  ├─ data/
│  │  └─ mock_data.dart      # 与概念稿一致的 Mock 文案与数字（M2 用 API 替换）
│  ├─ widgets/               # 复用组件（全部自绘或无依赖实现）
│  │  ├─ pulse_card.dart     # 白卡：18 圆角 + 1px 细边 + 极轻阴影
│  │  ├─ section_header.dart, status_chip.dart, mini_button.dart
│  │  ├─ pulse_icon_button.dart, pulse_toggle.dart, segmented_control.dart
│  │  ├─ list_tile_row.dart, stat_tile.dart, highlight_text.dart
│  │  ├─ pulse_ring.dart     # CustomPainter 渐变健康环（含 2.4s 呼吸）
│  │  ├─ sparkline.dart      # CustomPainter 折线 / 面积 / 虚线阈值
│  │  ├─ week_bars.dart      # 近 7 天柱状图
│  │  ├─ pulse_dock.dart     # 4 tab + 中央渐变 AI 光球
│  │  ├─ ai_card.dart        # AI 洞察卡（左侧渐变竖条 + 操作按钮）
│  │  ├─ workshop_map.dart   # 车间地图（网格 + 分区 + 设备点）
│  │  ├─ twin_scene.dart     # 数字孪生占位 3D 场景（等距体块 + 热点标签）
│  │  ├─ twin_detail_sheet.dart, ai_answer_card.dart, ai_input_bar.dart
│  │  └─ device_card.dart, scan_card.dart
│  └─ screens/
│     ├─ overview_screen.dart   # 01 总览
│     ├─ ai_screen.dart         # 02 AI 对话（全屏路由）
│     ├─ devices_screen.dart    # 03 设备（列表 / 地图 / 巡检）
│     ├─ alerts_screen.dart     # 04 报警（时间线）
│     ├─ profile_screen.dart    # 05 我的
│     └─ twin_screen.dart       # 06 数字孪生（全屏路由）
└─ test/
   └─ smoke_test.dart       # 首屏渲染 + dock 切换冒烟
```

## 导航结构

- 根：`Scaffold` + 页面渐变底 + `IndexedStack`（总览 / 设备 / 报警 / 我的）+ 固定底部 `PulseDock`。
- 中央光球 → `Navigator.push` 全屏 `AiScreen`（不占 tab）。
- 设备页地图卡 / 设备卡 / 报警「查看趋势」→ 全屏 `TwinScreen`。
- `TwinScreen` 底部 sheet 的「AI 诊断」→ 再 push `AiScreen`；返回逐级 pop。
- 所有页面 `SafeArea` + 纵向滚动，内容底部留 120 左右 padding 给 dock 让位。

## 设计 token（`lib/theme/pulse_theme.dart`）

| 类别 | Token | 值 |
| --- | --- | --- |
| 背景 | `bg` / `bgTop` | `#F4F5F7` / `#F8F9FB`（页面渐变 `#F8F9FB → #F5F6F9 → #F4F5F7`）|
| 卡片 | `card` / `card2` | `#FFFFFF` / `#F8F9FB` |
| 文字 | `ink` / `text` / `sub` / `dim` | `#0B1220` / `#101828` / `#667085` / `#98A2B3` |
| 分割 | `line` / `line2` | `#EAECF0` / `#F2F4F7` |
| 主色 | `accent` / `accent2` / `accentSoft` | `#3D5AFE` / `#8B5CF6` / `#EEF2FF` |
| 语义 | `green` / `amber` / `red` | `#12B76A` / `#F79009` / `#F04438`（各带 soft / line / ink）|
| 圆角 | `chip` / `card` / `hero` / `dock` / `sheet` | `999` / `18` / `24` / `24` / `26` |
| 阴影 | `shadow.card` / `shadow.dock` | `0 1 2 rgba(16,24,40,.03)` / `0 12 32 rgba(16,24,40,.13)` |
| 字号 | `score` / `metricValue` / `cardTitle` / `body` / `meta` | `44` / `24` / `13.5` / `12` / `9.5` |

规则：主 CTA 墨黑底白字；蓝 / 紫只用于数据、AI、开关；卡片 18–22 圆角 + 1px 细边 + 极轻阴影；
所有数字使用 `PulseText.tabular`（`FontFeature.tabularFigures()`）保证跳动时不抖动。
不使用 emoji、不打包图片与字体，图标一律 Material Icons，图表 / 场景一律 `CustomPainter`。

## 六屏实现要点

1. **总览**：问候 + 定位 + 铃铛/扫码；三枚状态 chips（系统在线 / 7/7 设备 / 延迟 38ms）；
   148 渐变健康环 92%（较昨日 +3）；2×2 指标卡（温度 27.4 / 湿度 52.1 / 气压 1012 / 振动 0.18）带 sparkline；
   AI 洞察卡（追问 AI / 查看设备 / 忽略）；最新报警迷你卡。
2. **AI 对话**：顶栏 + 上下文 chips；用户气泡；`Orchestrator · 3 个 Agent 协作 · 6.2s`；
   结论卡（整体运行正常，振动略高于基线）+ 3 指标；近 24h 振动趋势 + 阈值虚线；
   工具轨迹（实时数据 / 历史趋势 / 维护手册）；3 条分析要点；快捷操作；底部输入栏（+ / 语音 / 发送）。
3. **设备**：列表 / 地图 / 巡检分段；在线 7 · 维护 1 · 离线 0，同步 38ms；
   3 张设备卡（运行中 / 3D / 维护中）；车间地图卡（网格 + 分区 + 设备点 + 数字孪生入口）；扫码接入新设备卡。
4. **报警**：全部 12 / 严重 2 / 警告 4 / 提示 6 筛选；4 条时间线（严重红 / 警告琥珀 / 提示紫）；
   报警推送 Switch 卡（飞书群 + App 通知 · 免打扰 22:00–07:00）；AI 复盘卡；近 7 天柱状图 18 条 · -22%。
5. **我的**：头像「李」+ 李工 / 管理员 · 上海某厂 · 一号车间；公网服务器绿卡（TLS 1.3 / 38ms）；
   6 行配置入口；报警推送 Switch；运维工具 3 行。
6. **数字孪生**：图层开关 + 分区 chips（全部 7 / 泵组区 3 / 装配区 2 / 配电区 2）；
   `CustomPainter` 等距地面网格 + 分区色块 + 设备体块 + 热点标签（3 号泵组选中高亮）；
   右侧 +/−/复位缩放（1.0–1.6）；图例（运行 5 / 关注 1 / 维护 1）；底部指标 sheet（振动 0.18 / 温度 27.4 / 电流 4.2、
   近 24h sparkline + 阈值 0.5、AI 诊断 / 查看趋势 / 立方体按钮）。

## M1 与真实数据的映射（M2 TODO）

M1 全部数据来自 `lib/data/mock_data.dart`，字段形状已按 M0 接口对齐，替换时按下面的对应关系接线：

| Mock 位置 | M2 接口 | 说明 |
| --- | --- | --- |
| 服务器卡片 / 延迟 | `GET /api/mobile/bootstrap`、`GET /api/system/health` | server.name/version/time，health.api/mysql/ollama/feishu |
| 6 行配置（阈值、设备、AI、知识库、飞书、审计）| `GET /api/mobile/config-schema` | groups[].fields[]：key/label/type/unit/current；PATCH 时带 base_version，处理 409 / 422 |
| 设备列表 / 概要 | `GET /api/devices`、`GET /api/device` | devices[].{id,name,status,model_url,twin.position} |
| 数字孪生分区与热点 | `GET /api/twin/scene` | scene.zones[]（position/size/color）+ devices[].twin.{position,rotation,zone} |
| 报警时间线 / 计数 | `GET /api/alerts?level=&status=&cursor=&limit=20` | POST /api/alerts/{id}/handle（handle / silence / ignore）|
| AI 对话 | `WS /ws/chat?token=` + `GET /api/twin/scene` 上下文 | 消息 {type,seq,ts,data}；Orchestrator 步骤改为流式轨迹 |
| 实时指标（温度 / 振动 …）| `WS /ws/sensor?token=` | 5s 心跳；断线重连 + 本地缓存 |
| 推送开关 | `POST /api/mobile/push-token` / `DELETE` | 飞书群 + App 通知，免打扰时段本地存储 |
| 登录 / token | `POST /api/mobile/login` | 返回 token/expires_in/user/server；存储用 secure_storage |

其余 M2 事项：

- 状态管理（Riverpod 或 Bloc）+ go_router（当前是 `Navigator.push` 直连）
- dio 网络层 + 统一错误 / 版本冲突（409）提示；`web_socket_channel` 负责两条 WS
- `TwinScreen` 走路线 A：`WebView` 承载复用 Web 端 Three.js 场景（`model_url` / `model_filename` 已有字段），
  Flutter 侧只保留 chips / 图例 / 底部 sheet，用 JS bridge 同步选中设备
- 登录页、空态 / 骨架屏 / 下拉刷新、错误提示；报警处理二次确认
- 语音输入（麦克风按钮当前为占位）、扫码接入（当前为占位）
- 适配：Android 8.0（API 26）arm64-v8a，鸿蒙 4 兼容 APK；字号随系统缩放做溢出保护

## 已知限制

- 所有交互按钮中未接后端的动作统一走 `SnackBar`「… · M2 接入真实接口后启用」。
- 数字孪生是 `CustomPainter` 占位场景，不支持真实旋转 / 缩放模型（只有整层 Transform 缩放）。
- 未接入真实字体文件，依赖系统字体（PingFang SC / HarmonyOS Sans / MiSans / 微软雅黑 等 fallback）。
- 代码约定：单文件 < 500 行；所有 import 使用 `package:pulse_mobile/...`；无网络资源。
- 验证方式为 `flutter analyze` + `flutter test`（本机无 SDK，尚未实际执行；接入 CI 后请先跑这两条）。

## 版本

M1 概念版 · v0.1.0
