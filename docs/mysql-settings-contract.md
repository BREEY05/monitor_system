# MySQL 迁移与设置界面契约（v1）

本文件由 Lead 维护，是 api_server.py（Lead）与 static/index.html 设置页（settings-ui）之间的接口约定。任何一方改动需先在本文件登记。

## 1. 目标

1. 数据库从 Supabase PostgreSQL 彻底切换为 MySQL（本机可运行、可配置、可测试、可回退 SQLite）。
2. 设备模型改为本地存储，不再使用 Supabase Storage。
3. 设置页 / 设备配置页重做，覆盖数据库连接、设备模型、阈值报警三块核心配置。

## 2. 配置字段（config.json）

移除 supabase_url、supabase_key、supabase_storage_bucket、postgres_dsn。
新增并持久化：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| database_backend | mysql | mysql 或 sqlite；mysql 连接失败自动回退 sqlite |
| mysql_host | 127.0.0.1 | MySQL 主机 |
| mysql_port | 3307 | 端口（便携实例用 3307） |
| mysql_user | root | 用户名 |
| mysql_password | 空字符串 | 密码；GET /api/settings 不返回该字段（hidden） |
| mysql_database | monitor_system | 库名；不存在时后端自动 CREATE DATABASE |

database_backend=mysql 时，启动阶段自动建库建表、并从 app_settings 加载配置；连接失败时日志警告并回退 SQLite，页面通过 /api/database/status 看到 fallback=true。

## 3. 后端接口

### 3.1 GET /api/database/status

返回当前生效状态，供设置页状态条使用：

    {
      "backend": "mysql",
      "configured": true,
      "connected": true,
      "fallback": false,
      "host": "127.0.0.1",
      "port": 3307,
      "user": "root",
      "database": "monitor_system",
      "server_version": "8.0.42",
      "table_count": 12,
      "message": "MySQL 已连接（monitor_system）"
    }

连接失败/回退 SQLite 时：backend="sqlite"、configured=true、connected=false、fallback=true、server_version 为空、message 说明原因（中文，不含堆栈）。
后端为 sqlite 且未配置 mysql 时 configured=false。

### 3.2 POST /api/database/test

请求体（全部可选，缺省用当前 CONFIG；空字符串也视为缺省）：

    {
      "mysql_host": "127.0.0.1",
      "mysql_port": 3307,
      "mysql_user": "root",
      "mysql_password": "",
      "mysql_database": "monitor_system"
    }

只做连接测试，不落盘、不改 CONFIG、不影响正在运行的连接。成功：

    {"success": true, "message": "MySQL 连接成功（MySQL 8.0.42，monitor_system）", "server_version": "8.0.42", "database": "monitor_system", "tables": 12}

失败：

    {"success": false, "message": "MySQL 连接失败：Can't connect to MySQL server on ..."}

超时上限约 5 秒，错误信息截断到 300 字符。

### 3.3 POST /api/settings（数据库相关）

请求体可包含 database_backend、mysql_host、mysql_port、mysql_user、mysql_password、mysql_database 以及原有 thresholds、alarm_trigger_count、alarm_window_seconds、devices 等。规则：

- 请求里没有 mysql_password 键时保留原密码；显式传空字符串表示清空密码。
- 保存后若 database_backend=mysql，后端立即初始化 MySQL、写入配置与设备表，返回最新状态。
- 响应（在原 success/cloud_saved/backend 基础上增加 database 与 message）：

    {"success": true, "cloud_saved": true, "backend": "mysql", "database": {...同 3.1...}, "message": "数据库配置已保存并完成初始化"}

- 若 MySQL 初始化失败：success=false、backend="sqlite"、message 为中文原因，config.json 仍保存用户填写的参数以便修正。

### 3.4 POST /api/device/model（本地存储）

multipart：file + device_id（可选，缺省当前选中设备）。仅 .glb/.gltf/.bin，≤80MB。
响应：

    {"success": true, "device_id": "device-1", "model_url": "/static/uploads/device_models/xxx.glb", "filename": "xxx.glb", "storage_backend": "local", "cloud_saved": true}

失败返回 400/502 + detail 中文。设置页据此提示「模型已保存到本地」。

## 4. 设置页 UI 要求（settings-ui 负责）

只允许改 static/index.html 中设置页的 CSS、markup 与相关 JS，不改其他页面、不改 api_server.py、不改 equipment.html/scene.js。

### 4.1 页面结构

设置页改为顶部横向**分组标签页**，一次只显示一个分组，避免两列错位与超长滚动：

1. 数据库与存储（单卡）
2. 设备配置与 3D 模型（单卡）
3. 阈值与报警（单卡）
4. AI 与 Skill（双卡并排：#settings-ai + #settings-skill）
5. 飞书与地图（双卡并排：#settings-feishu + #settings-map）

实现约定：.settings-layout 默认单列、max-width 1120px 居中；含两张卡的分组给容器加 .is-dual（两列等宽），≤1100px 回到单列。顶部 .settings-nav 使用 position: sticky（top:12px），在内容区滚动时保持可见。切换由 activateSettingsPanel(panelKey) 完成：按钮 active/aria-selected/tabIndex、卡片 .is-panel-active、localStorage 键 monitor_settings_tab；旧值 settings-skill/settings-map 通过别名映射到 settings-ai/settings-feishu。键盘左右方向键可切换标签页。现有 .setting-group 复用，但保留卡片标题栏与状态标签。

### 4.2 数据库卡片

- 状态条：数据库类型（MySQL/SQLite）、连接状态圆点与文案、服务器版本、库名；数据来自 GET /api/database/status，页面进入设置页时调用一次，保存/测试后刷新。
- 表单字段（2 列 grid）：数据库类型 select（MySQL / SQLite 本地）、主机、端口（number）、用户名、密码（password，placeholder「留空表示不修改」）、数据库名。
- 按钮：测试连接（调 3.2）、保存并初始化（调 3.3）。测试期间按钮禁用并显示「测试中…」，结果写入卡片内联消息区（成功绿色 / 失败红色），不用 alert。
- 底部提示：如何启动本机 MySQL（见 docs/mysql-setup.md，若尚未生成可写「见项目 README 的 MySQL 章节」）。
- 禁止再出现 Supabase URL/Key/Bucket 任何输入项；旧 localStorage 中 supabase_* 键可保留清理逻辑，但界面不得展示。

### 4.3 设备配置卡片

- 顶部：设备下拉（#deviceEditSelect）+「新增设备」按钮 + 当前选中设备模型状态标签（已上传 / 内置模型 / 未配置）。
- 表单：设备名称、编号（只读或自动生成）、工位序号（只读展示）、经度、纬度、注册日期、运行状态、3D 模型文件（file input 只接受 .glb/.gltf/.bin）+「上传模型」按钮 + 模型文件名/来源提示。
- 保存按钮：保存后 toast + 内联成功提示；刷新设备下拉与孪生 iframe 配置（若 window.postEquipmentConfig 存在则调用）。
- 上传成功后将返回的 model_url / filename 填回当前编辑对象，并显示「本地存储 · xxx.glb」。
- 设备列表下方的「新增设备」流程：生成 id（device-<毫秒时间戳>）、默认名称 工业设备 #NN、清空表单并聚焦名称输入框，保存后出现在下拉中。
- 保留现有设备保存逻辑的兼容：POST /api/settings 的 devices 数组格式不变（id,name,latitude,longitude,registered_at,status,model_url,model_filename）。

### 4.4 阈值与报警卡片

- 温度/湿度/振动三个数字输入，显示单位与建议范围；后端加载值回填（/api/settings 的 thresholds）。
- 「保存阈值」按钮：POST /api/settings {thresholds:{temperature,humidity,vibration}}，成功 toast。
- 报警触发次数 slider 保留，数值实时显示；单独「保存报警设置」或合并到阈值卡片保存按钮，明确提示。
- 输入非法（空/非数字/负数）时红框 + 内联错误，不发请求。

### 4.5 通用

- 新增全局 toast 函数（右下角，3 秒消失，成功/失败两种样式）；设置页不得再用 alert()。
- 所有文案中文、无 emoji；沿用现有设计变量（--brand 等）与卡片风格；不改左侧导航与其他页面 DOM。
- 不得破坏父页与数字孪生 iframe 的既有集成（static/index.html:2485 iframe、2885 描述、4052/4082 消息监听、postEquipmentConfig）。
- 页面加载后设置页的原有回填逻辑必须仍工作；saveSettings() 保留供其他分组调用，但移除 supabase_* 字段。

### 4.6 供 Lead 验收的元素 ID（必须存在且唯一）

#dbStatusChip #dbStatusText #dbBackendSelect #mysqlHostInput #mysqlPortInput #mysqlUserInput #mysqlPasswordInput #mysqlDatabaseInput #dbTestBtn #dbSaveBtn #dbMessage
#deviceEditSelect #createDeviceBtn #deviceNameInput #deviceLongitudeInput #deviceLatitudeInput #deviceRegisteredInput #deviceStatusInput #deviceModelInput #uploadModelBtn #saveDeviceBtn #deviceModelStatus #deviceFormMessage #deviceSourceText
#tempThreshold #humidThreshold #vibThreshold #saveThresholdBtn #thresholdMessage #anomalyCountSlider #anomalyCountValue
#toastHost

## 5. 自测与交付

- 用 Playwright（.local-tools/node_modules/playwright，channel:'msedge'）对 http://127.0.0.1:8000 设置页做截图与断言：1440×900、1024×768 两档无横向溢出；字段/按钮齐全；mock /api/database/test 与 /api/settings 成功/失败两种响应验证状态条与内联消息；设备下拉切换回填；阈值非法输入拦截。
- 后端可能由 Lead 同步修改，接口未就绪时用 page.route 模拟，交付前以真实后端为准复核一遍。
- 交付报告：改动文件、新增/保留 ID 清单、截图路径、未解决问题。
