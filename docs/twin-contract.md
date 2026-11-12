# 数字孪生页面（设备情况）重构契约 v5

本轮目标（用户 m00001）：按 README 继续优化项目；优先完善「设备情况 / 数字孪生」页面的布局与交互。
架构保持不变：static/index.html 内 iframe 加载 static/equipment.html，equipment.html 引入 static/equipment-scene.js（Three.js 场景）。

## 文件所有权（禁止越界）

| 文件 | 负责人 | 说明 |
| --- | --- | --- |
| static/equipment.html | twin-ui | 新布局 + 全部 CSS + 静态 DOM（不含业务 JS） |
| static/equipment-scene.js | twin-scene | Three.js 场景、数据轮询、全部交互与 DOM 填充 |
| docs/twin-contract.md | lead | 本契约 |
| api_server.py（/api/twin/overview） | lead | 已实现并上线 |
| static/index.html（iframe 版本号、postMessage 处理） | lead | Lead 负责，其他成员不要改 |

不要修改对方的文件；不要改 config.json；不要重启/占用 8000 端口；不要提交 git（目录不是 git 仓库）。

## 设计基调

浅色工业控制台风格，与父页面一致：背景 #eef2f8，面板 #fff，边框 #dbe3ee，主色 #1d4ed8，正文 #24344a，次要文字 #6b7c93，成功 #0f8a5f，警示 #b7791f，危险 #d64545，圆角 8px，面板阴影 0 1px 2px rgba(16,32,56,.05)。字体沿用 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif；数字使用 font-variant-numeric: tabular-nums。禁止 emoji 图标；图标用内联 SVG（stroke=currentColor, 12–14px）或纯文字，风格克制。

页面在 iframe 内完全铺满，不出现整页滚动条；面板内部可滚动。1440×900 下父页面 iframe 内容区约 1136×750，min-height 620。

## 布局蓝图

body > main#twinApp.twin-app，两行 grid：auto minmax(0,1fr)，gap 10px，padding 10px 12px 12px。

### 1) 顶部状态条 header.twin-top（面板卡片样式）
- 左：标题「设备情况」+ 小徽标「数字孪生」；副标题「生产间 · 实时三维监控」。
- 中：KPI 组（6 项，竖向分隔线）：设备总数 #kpiTotal、运行中 #kpiOnline、告警设备 #kpiAlert、车间温度 #kpiTemp、车间湿度 #kpiHumidity、车间振动 #kpiVibration。值用 17–18px 650，单位 11px muted；#kpiAlert 所在项在值 >0 时由 JS 加类 has-alert 变红。
- 右：实时连接胶囊 #livePill（内部 i 圆点 + span#livePillText）、更新时间 #updateTime、「刷新」按钮 #refreshBtn（type=button，带 ↻ SVG）。
- 窄屏（<900px）KPI 横向滚动，不换行挤压标题。

### 2) 主体 main.twin-main
默认 grid-template-columns: 232px minmax(0,1fr) 296px; gap 10px; min-height:0。
- @media (max-width:1079px)：两列 200px minmax(0,1fr)；#inspector 改为 grid-column:1/-1、两列卡片网格、页面允许纵向滚动（body overflow:auto，#twinApp height:auto;min-height:100%），舞台固定高度 520px。
- @media (max-width:719px)：单列；舞台 420px；侧栏设备列表横向滚动；inspector 单列。

#### 2a) 左栏 aside#sidebar.panel
flex 纵向，14px 内边距，min-height:0。
- 标题行「设备总览」+ #assetCount（如「3 台」）。
- 搜索框 #search（带 SVG 放大镜，placeholder「搜索设备名称 / 编号」）。
- 状态筛选 chips：按钮 .chip#filterAll（默认激活）、#filterRunning、#filterAlert、#filterOffline，文案「全部 / 运行 / 告警 / 离线」，用 aria-pressed 表示激活，JS 同时维护 .is-active。
- 分组标签「生产间 / 设备工位」；#tree 设备列表；#sidebarEmpty 空态（默认 .is-hidden）。
- 列表项按钮 .device-item[data-device-id]，内容三行结构：
  - .device-item-head：span.device-dot + span.device-name + 右侧 span.device-alarm-badge（告警数，0 时隐藏）
  - .device-meta：工位 01 · device-1
  - .device-tags：状态标签 .tag（运行中/告警/离线）+「模型」标签（有模型时）
  状态由 JS 加 .is-active / .is-alarm / .is-offline / .is-dim 类。
- 底部 .sidebar-legend（margin-top:auto）：运行 / 告警 / 无数据 / 离线 四色点。
- 键盘提示小字：单击选中 · 双击单机 · Esc 返回。

#### 2b) 中栏 section#stage.panel（核心视图，position:relative; overflow:hidden）
- 顶部工具栏 .stage-toolbar：高 48px，不换行，横向可滚动（小屏）。
  - 左：h2#stageTitle「车间总览」+ p#stageSubtitle「3 台设备 · 车间总览」。
  - 右：按钮组 .stage-tools（均 type=button，class 为 tool-btn）：#plantBtn「车间总览」、#frontBtn「正视」、#labelsBtn「标签」、#rotateBtn「自动旋转」、#fullscreenBtn「全屏」、#snapshotBtn「截图」、#resetBtn「复位」。切换类按钮（标签/自动旋转）用 .is-active + aria-pressed；#plantBtn 在车间模式时 .is-active。
- #canvasWrap.canvas-wrap：position:absolute; inset:48px 0 0 0; canvas 填满；dataset 测试钩子：data-scene-ready="1"、data-model-count（工位总数）、data-configured-count（成功加载 GLB 数）、data-selected-id。
- #labels.labels：与 canvasWrap 同定位，pointer-events:none；内部 .model-label[data-device-id]（pointer-events:auto; cursor:pointer）小胶囊，.is-active / .is-alarm 样式。
- #deviceTip.device-tip：绝对定位悬浮提示，默认 .is-hidden，内部 strong#tipName + span#tipMeta。
- #stageHud.stage-hud：左下角悬浮卡，默认 .is-hidden；内部 #hudStatus（状态胶囊）、#hudName、#hudMeta（工位 · 型号）、三列指标 #hudTemp / #hudHumidity / #hudVibration（各自含数值与单位，小字号）、按钮 #hudOpen「进入单机」。
- #stageHint.stage-hint：底部居中操作提示「拖拽旋转 · 滚轮缩放 · 单击选中 · 双击进入单机」。
- .axis#axisBox：右下角坐标轴卡（80×80），canvas#axisCanvas width=140 height=114 + 小字「Y UP / WORLD」。
- #stageToast.stage-toast：顶部居中轻提示，默认 .is-hidden（1.8s 自动隐藏）。
- #stageLoading.stage-loading：加载遮罩（spinner + #stageLoadingText「正在装配三维场景…」），场景就绪后 .is-hidden。
- #stageError.stage-error：WebGL/初始化失败遮罩，默认 .is-hidden，内部 #stageErrorText。

#### 2c) 右栏 aside#inspector（flex 纵向 gap 10px，overflow:auto，min-height:0）
5 张 .panel.card：
1. 设备信息：标题「设备信息」+ #partIndex（如 1/3）；#partName（15px 650）；信息行：设备编号 #partCode、对应工位 #stationName、模型文件 #modelFile、运行状态 #partStatus（胶囊 span，JS 设 textContent 与 .state-* 类）、传感来源 #partSource、注册日期 #partRegistered；按钮行 #openDevice「单机查看」（primary）、#openSettings「设备设置」。
2. 实时工况：标题 + #sensorBadge 小徽标；#sensorMetrics 内三行 .metric-row（标签 / 数值 #metricTempValue、#metricHumidityValue、#metricVibrationValue / 阈值 #metricTempNote 等 / 进度条 .metric-bar > span#metricTempBar 等 宽度百分比）；#sensorUpdated 小字「更新于 --」；#sensorEmpty 空态（默认 .is-hidden）「暂无实时传感数据」。
3. 风险与预测：标题 + #riskBadge 胶囊；#riskScore 大号数字（0–100）；#riskReasons ul 列表；#riskNote 小字说明。
4. 最近告警：标题 + #alertCount 徽标；#alertList 列表（条目 .alert-item，左侧色条，含标题、区域/设备、HH:MM:SS 时间）；#alertEmpty 空态；#alertMore「查看全部告警」文本按钮。
5. 模型装配：标题「模型装配」；#assemblyInfo 一段说明；#modelNote 小字（模型来源/回退说明）。

## 交互行为（twin-scene 实现）

### 数据
- 每 3s 轮询 GET {apiUrl}/api/twin/overview（apiUrl 来自父页 postMessage 或 location.origin）；document.hidden 时暂停，visibilitychange 时立即刷新。
- 初始设备来源：父页 postMessage {type:'monitor-config', apiUrl, devices}；若 400ms 内未收到，则 fetch {apiUrl}/api/settings 兜底。overview.devices 为权威数据，按 id 合并（配置有、overview 无的设备也要展示）。
- 首次 load 后向父页 postMessage {type:'equipment-ready'}；收到 monitor-config 后立即重渲染并刷新。
- 请求失败：保留上次数据；#livePill 加 .is-error 文案「数据接口断开」；#stageToast 提示「数据接口连接中断，正在重试…」；退避 5s 重试，成功后恢复。
- 成功时 #updateTime 显示「更新 HH:MM:SS」（overview.generated_at）。

### 3D 场景
- 保留现有技术栈：importmap（three / three/addons/）、GLTFLoader、OrbitControls；renderer preserveDrawingBuffer:true，antialias，pixelRatio ≤2。
- 场景：浅色车间（地板浅灰 + 网格线 + 后墙/立柱 + 每个工位地面黄色或蓝色标线 + 工位编号贴地文字可用 CanvasTexture 或省略），灯光 HemisphereLight + DirectionalLight；选中设备下方显示环形高亮（three 对象），告警设备有红色脉冲外框（复用 EdgesGeometry 包围盒线框）。
- 模型：优先加载 model_url 的 GLB；加载中/失败用简化设备外形（沿用现有 simplified() 思路）；模型归一化居中落地；所有材质不影响可读性。重建场景时释放旧 geometry/material/texture。
- 相机：位置/目标用 650ms easeInOutCubic 补间；单击设备或列表项聚焦该设备并选中；双击进入单机模式（只显示该设备+局部地台，#stageTitle 变为设备名）；Esc / #plantBtn 返回车间总览；#resetBtn 复原默认机位与缩放。
- 悬停：pointermove 节流 80ms raycast；命中设备时显示 #deviceTip（跟随鼠标，显示设备名 + 工位/状态），光标 pointer，列表对应项加 .is-hover；未命中隐藏。注意与拖拽区分（位移 <5px 才算点击）。
- 标签：投影定位（每帧）；标签可见时点击标签选中设备；#labelsBtn 切换 #labels 的 .is-hidden 并同步 aria-pressed。
- #rotateBtn：OrbitControls.autoRotate 开关，按钮 .is-active / aria-pressed 同步；用户拖拽不关闭。
- #fullscreenBtn：对 #stage 调用 requestFullscreen / exitFullscreen，全屏状态变化时同步按钮文案（全屏/退出全屏）与 .is-active；不支持时 toast「当前浏览器不支持全屏」。
- #snapshotBtn：renderer.render 后 canvas.toDataURL('image/png') 下载 twin-YYYYMMDD-HHmmss.png；toast「截图已保存」。
- 键盘（焦点在 input/textarea 时不拦截）：Esc 返回车间；Enter 进入选中设备单机；r 复位；f 正视；l 标签；空格 自动旋转；↑/↓ 在设备间切换选中。
- #openSettings：postMessage {type:'equipment-settings', deviceId}；#alertMore：postMessage {type:'equipment-alerts'}；selection 变化可 postMessage {type:'equipment-select', deviceId}（父页可忽略）。

### 数据渲染
- KPI：#kpiTotal=summary.total；#kpiOnline=summary.online；#kpiAlert=summary.alerting（>0 加 has-alert）；温度/湿度/振动取 plant 值，1/1/2 位小数，无数据为「--」。
- #livePill 状态：source.online → .is-online，文案「实时 · {age}s」；source.stale → .is-stale「已过期 {age}s」；type==='none' → .is-idle「暂无实时数据」。
- 左列表：每项状态：alerts.open>0 → 告警标签/红点/.is-alarm 与徽标数字；否则 device.online=false → 离线灰点/.is-offline；否则「运行中」绿点。筛选与搜索只影响列表显示（不改变选中）；过滤后无结果时显示 #sidebarEmpty「没有匹配的设备」。
- 选中设备：#partIndex={index+1}/{total}；#partName=name；#partCode=id；#stationName=station；#modelFile=model_filename 或「未配置」；#partStatus 文案：告警 n → 「告警 n」.state-danger；离线 → 「离线」.state-offline；否则「运行中」.state-normal；#partSource=sensor_bound ? '设备直连传感' : (plant.available ? '车间共享传感' : '暂无数据')；#partRegistered 可选显示（无字段显示「—」）。
- 工况卡固定展示 plant（车间共享传感）：数值 + 单位（°C / %RH / mm/s），进度条宽度 = min(value/threshold*100,100)%，颜色按 statuses（normal 绿 / warning 黄 / danger 红），阈值注释「阈值 {threshold}」；#sensorUpdated「更新于 {HH:MM:SS}」；plant.available=false 时隐藏 #sensorMetrics、显示 #sensorEmpty、#sensorBadge 文案「暂无数据」。
- 风险卡：选中设备 risk.risk_level 映射 NORMAL→「正常」/WATCH→「关注」/WARNING→「预警」/CRITICAL→「严重」，对应 .risk-normal/.risk-watch/.risk-warning/.risk-critical；#riskScore 显示 risk_score（1 位小数）；#riskReasons 逐条 li（reasons 可能为空时显示「暂无风险说明」）；#riskNote 根据 risk.data_scope：device→「基于设备直连实时数据与近期告警」；plant→「基于车间共享传感与近期告警」；none→「暂无实时数据，仅基于近期告警」。
- 告警卡：#alertCount「未处理 n」；取 alerts.items 前 5 条；条目显示 level 颜色、title、source/area、HH:MM:SS；点击条目若 device_id 匹配已配置设备则选中它，否则 toast「该告警来自未配置的传感设备」；无告警显示 #alertEmpty「当前没有未处理告警」。
- HUD：选中时显示，内含状态、名称、工位、三项 plant 数值；#hudOpen 进入单机；未选中隐藏。
- 模型装配卡：#assemblyInfo 显示「n 个工位 · m 台配置模型 · k 台回退外形」；#modelNote 显示当前模型文件名与来源（配置模型 / 内置外形）。

### 无障碍与健壮性
- 所有按钮 type="button"；纯图标按钮必须有 aria-label/title；input 有 aria-label。
- 焦点可见：:focus-visible 2px 外发光。
- 所有 getElementById 做空值保护（HTML 修改后仍不崩溃）；场景初始化 try/catch，WebGL 失败时显示 #stageError。
- 不引入外部 CDN/新依赖；不使用 alert()/confirm()。

## 后端契约（已上线，可用 curl 验证）

GET http://127.0.0.1:8000/api/twin/overview 返回示例（字段必须按此读取，允许额外字段）：

{
  "generated_at": "2026-11-08T13:14:55.900000",
  "source": {"type": "raspberry-live", "timestamp": "...", "age_seconds": 0, "stale": false, "online": true, "device_id": "raspberry-pi-5", "area": "A区", "label": "树莓派实时上报", "interval_seconds": 5},
  "thresholds": {"temperature": 31.0, "humidity": 60.0, "vibration": 0.5},
  "plant": {"available": true, "temperature": 25.4, "humidity": 48.2, "pressure": 1012.5, "vibration": 0.12, "statuses": {"temperature": "normal", "humidity": "normal", "vibration": "normal"}, "timestamp": "..."},
  "devices": [{"id": "device-1", "name": "工业设备 #01", "status": "运行中", "online": true, "station": "工位 01", "index": 0, "model_url": "...", "model_filename": "blender.glb", "has_model": true, "sensor_bound": false, "risk": {"device_id": "device-1", "risk_score": 0.0, "risk_level": "NORMAL", "components": {"current": 0, "prediction": 0, "history": 0, "proximity": 0}, "reasons": ["..."], "data_scope": "plant", "current_data_available": true, "prediction_status": "not_requested"}, "alerts": {"open": 0, "latest_at": null}}],
  "alerts": {"open_total": 0, "items": [{"id": 1, "title": "温度异常", "time": "...", "source": "A区", "level": "warning", "type": "temperature", "value": 32.1, "threshold": 31.0, "device_id": "raspberry-pi-5", "area": "A区", "handled": false}], "by_device": {}},
  "summary": {"total": 3, "online": 3, "alerting": 0, "data_online": true}
}

statuses 取值：normal / warning / danger / missing。当前树莓派 device_id 通常为 raspberry-pi-5，与配置设备 id 不一致，因此 sensor_bound 多为 false，页面应正常显示「车间共享传感」。

## 父页面协议（Lead 维护，供参考）

- 父页 postMessage：{type:'monitor-config', apiUrl, devices:[{id,name,status,model_url,model_filename,...}]}。
- iframe postMessage：{type:'equipment-ready'}、{type:'equipment-settings', deviceId}、{type:'equipment-alerts'}。
- static/index.html 的 iframe src 已为 /static/equipment.html?v=6，iframe 内 script 为 /static/equipment-scene.js?v=6。改动这两个文件后必须同步 bump 版本号（v6→v7），否则浏览器可能命中旧缓存。

## 验收清单（Lead 用 Playwright + 截图验收）

1. 打开 http://127.0.0.1:8000/ → 左侧「设备情况」→ iframe 加载后无页面 JS 错误；#canvasWrap[data-scene-ready="1"] 出现；#canvasWrap[data-configured-count] 应为 3（三台设备均绑定本地 GLB，见 v7 更新记录）。
2. 桌面 1440×900：无整页滚动、无横向溢出；顶部 6 个 KPI 有值；右侧 5 张卡片信息完整；3 台设备列表可见。
3. 点击列表项/3D 设备：右侧信息与 HUD 更新，相机补间聚焦；双击进入单机，#stageTitle 变化；Esc 返回。
4. 自动旋转、标签、正视、复位、截图按钮均生效且状态类正确；刷新按钮立即刷新时间。
5. 模拟实时数据（Lead 会 POST /api/raspberry/sensors）：KPI/工况卡/实时胶囊更新；数据过期后显示已过期。
6. 窄屏 1024×768 与 780×900：布局按断点重排，不溢出。
7. 代码层面：grep 无旧 ID 残留（如 viewTitle/viewSubtitle/overviewTitle/modelSummary/serviceState 等已废弃；axisCanvas 保留）；无未处理 Promise 异常；轮询在页面隐藏时暂停。

## 参考：现有可复用能力

旧 static/equipment-scene.js（463 行）已有：GLTFLoader 加载与 15s 超时、simplified() 内置外形、fitModel() 归一化、buildRoom() 车间、frameView()、raycaster 选中、标签投影、坐标轴绘制、告警轮询。twin-scene 可重构但应保留这些能力的实现思路，避免从零试错。

## 补充：父页可见性协议（Lead 已实现于 static/index.html）

父页在 switchPage 时向 iframe postMessage：{type:'equipment-visibility', visible:boolean}（进入设备情况页 visible=true，离开为 false）。equipment-scene.js 必须监听：visible=false 时暂停 /api/twin/overview 轮询与自动旋转计时，visible=true 时立即刷新一次数据并恢复轮询。若从未收到该消息，按 visible=true 处理（直接打开 equipment.html 调试时正常轮询）。

父页已处理的 iframe 消息：equipment-ready（回发配置）、equipment-settings（跳系统设置并选中设备）、equipment-select（同步父页选中设备）、equipment-alerts（跳报警中心并刷新列表）。

## 最终实现记录（v6，2026-11-08 Lead 验收）

- 右栏最终顺序：#partCard 设备信息 → #sensorCard 实时工况 → #alertCard 最近告警 → #riskCard 风险与预测 → #assemblyCard 模型装配；1136×750 首屏可见前 3 卡完整+第 4 卡标题，1440×900 前 4 卡完整。
- 交互定案：plant（车间总览）单击设备/列表项 = 选中并平滑聚焦该设备（不切换模式）；双击或「单机查看」= 进入单机；Esc/「车间总览」= 回到整体机位。整体机位在设备数量变化或 GLB 加载完成且用户未拖拽时自动重算（state.plantFramedCount + viewTouched）。

## 更新记录（v7，MySQL + 新模型，2026-11-08）

- 三台设备模型全部本地化（config.json）：device-1 → /static/uploads/device_models/cnc_machining_center.glb；device-1778465863105 → industrial_sensor_device_1778467857.glb；device-1778471165324 → pump_test_bench.glb。configured-count 由 1 变为 3，无回退外形。
- API 基址约定：#apiUrl 必须是后端 origin（默认 http://localhost:8000），Ollama 地址只允许放在 #ollamaApiUrl / #ollamaApiUrlSettings。equipment-scene.js 用 new URL(model_url, state.apiUrl + '/') 解析模型，因此 #apiUrl 被污染会直接导致模型 404。
- 已修复 bug：loadSystemSettings 曾用 settings.ollama_url 覆盖 #apiUrl，导致所有 /api/ 请求与模型 URL 指向 11434。现 saveSettings 只从 Ollama 专用输入读取 ollama_url，localStorage 键改为 monitor_ollamaUrl，旧 monitor_apiUrl 清除。
- 回归结果：verify-twin-v5.js 全部 ok（0 条 failed）；verify-twin-alert.js 32/32；verify-final.js 无 HTTP 4xx/JS 错误；1440×900 与 1136×750 无横向溢出。
- 告警视觉：3D 中告警设备显示红色脉冲包围线框，选中不再额外画蓝框；列表红点+徽标；KPI 告警设备红字。
- 已知限制（非代码缺陷）：三台设备中仅 device-1778465863105 的 GLB 为本地可用文件，device-1 与 device-1778471165324 的 Supabase 模型 URL 在本机不可解析，因此 data-configured-count 稳定为 1、另外两台显示内置简化外形；控制台对应 2 条资源级 ERR_NAME_NOT_RESOLVED/ERR_CONNECTION_CLOSED 属外部资源不可达，页面 JS 无异常。
- 已验证脚本：output/playwright/verify-twin-v5.js（真实数据布局/交互）、verify-twin-alert.js（route 注入告警与风险 fixture，32 项断言）、verify-twin-visibility.js（轮询暂停/恢复 6 项断言）。
