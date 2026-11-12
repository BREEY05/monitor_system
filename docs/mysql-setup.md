# MySQL 数据库接入说明

本项目默认使用 MySQL 存储业务数据（设备、告警、传感器历史、RAG 文档、Skill 等）。
数据库不可用时服务会自动回退到本地 SQLite（monitor_data.db），保证演示不中断。

## 1. 默认配置（config.json）

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| database_backend | mysql | mysql 或 sqlite |
| mysql_host | 127.0.0.1 | MySQL 地址 |
| mysql_port | 3307 | 项目便携 MySQL 使用 3307，避免与本机已有 MySQL 的 3306 冲突 |
| mysql_user | root | 用户名 |
| mysql_password | （空） | 保存后在 GET /api/settings 中不返回，仅返回 mysql_password_set |
| mysql_database | monitor_system | 库名，首次连接会自动 CREATE DATABASE IF NOT EXISTS（utf8mb4） |

## 2. 使用项目内置便携 MySQL（推荐，无需安装）

1. 确认 .local-mysql/mysql-8.0.42-winx64/bin/mysqld.exe 存在；
   若不存在，下载 MySQL 8.0.42 winx64 zip（https://cdn.mysql.com/archives/mysql-8.0/mysql-8.0.42-winx64.zip）
   并解压到 .local-mysql/ 目录，保持目录名为 mysql-8.0.42-winx64。
2. 双击 start_mysql.bat，或执行：
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_mysql.ps1
   脚本会：首次初始化数据目录 .local-mysql/data（root 空密码）、后台启动 mysqld、
   监听 127.0.0.1:3307、写入日志 .local-mysql/mysql.out.log 与 mysql.err.log。
3. 启动主服务（python start.py 或 start.bat）即可自动连接 MySQL；
   start.py 会在检测到便携 MySQL 时自动调用上述脚本。
4. 校验：GET http://127.0.0.1:8000/api/database/status 应返回
   connected: true、fallback: false、server_version、table_count > 0。

## 3. 使用本机已安装的 MySQL

把 config.json 中 mysql_port 改为 3306、填写 mysql_user / mysql_password，
在系统设置页「数据库与存储」中点击「测试连接」，通过后保存即可。
保存成功后后端会初始化全部数据表；失败的配置会返回 success=false 并给出原因。

## 4. 停止与重置

- 停止：任务管理器结束 mysqld.exe（仅结束项目目录下的那个进程）。
- 重置数据：停止 MySQL 后删除 .local-mysql/data，重新执行 start_mysql.bat 会自动重新初始化。
- 注意：删除 data 目录会丢失 MySQL 中的数据；SQLite 回退库 monitor_data.db 不受影响。

## 5. 故障排查

- 端口被占用：Get-NetTCPConnection -LocalPort 3307，结束占用进程，或改 config.json 的 mysql_port。
- 启动超时：查看 .local-mysql/mysql.err.log；若提示缺少 VC++ 运行库，安装
  Microsoft Visual C++ 2015-2022 Redistributable (x64)。
- 忘记 root 密码：停止 MySQL，删除 .local-mysql/data 后重新初始化（数据会清空）。
- 后端仍显示 fallback: true：确认 MySQL 已监听 3307、mysql_password 正确；
  后端对失败连接有 30 秒冷却，修正后重新保存设置或等待冷却结束。
- 服务端日志中「数据库: mysql - ...」行会打印实际使用的后端与连接状态。

## 6. 相关接口

- GET /api/database/status：只读状态（backend/configured/connected/fallback/version/table_count/message）。
- POST /api/database/test：用请求中的 mysql_* 字段做一次性连接测试，不修改配置。
- POST /api/settings：保存数据库配置并立即初始化；GET /api/settings 隐藏 mysql_password。
- POST /api/device/model：模型文件统一保存到 static/uploads/device_models/（本地存储，不再依赖云存储）。
