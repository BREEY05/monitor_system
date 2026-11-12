# 设备 3D 模型交付契约（v1）

本文件由 Lead 维护，模型交付方（twin-models）与集成方（Lead）共同遵守。

## 1. 要补的两个模型

项目现有 3 台设备，其中 2 台的模型文件已丢失/只剩外链（Supabase 不可用），需要重新制作并放到本地：

| 设备 | id | 用途 | 交付文件 |
| --- | --- | --- | --- |
| 工业设备 #01 | device-1 | 数控加工中心 CNC machining center | static/uploads/device_models/cnc_machining_center.glb |
| 工业设备 #03 | device-1778471165324 | 泵组试验台 pump test bench | static/uploads/device_models/pump_test_bench.glb |

设备 #02（device-1778465863105）已有可用模型 industrial_sensor_device_1778467857.glb，不要覆盖。

## 2. 视觉与坐标规范

- 工业设备写实风格，低到中等面数，轮廓在 3D 场景中 100~300px 高度下可辨认。
- CNC：立式加工中心形态——床身底座 + 立柱 + 主轴头 + 防护门/观察窗 + 操作面板 + 顶部警示灯；高度约为宽度的 1.5~1.8 倍。
- 泵组试验台：底座台架 + 电机 + 联轴器护罩 + 泵体 + 进出管口 + 压力表/控制箱；高度约为宽度的 1.0~1.2 倍。
- 配色参考现有车间浅色场景：机身浅灰 #dfe5ec / #c9d3df，深色底座与细节 #2f3b4d，品牌蓝 #1d4ed8 少量点缀，警示黄 #d97706 少量点缀。避免大面积纯白（场景背景为浅色）与纯黑。
- 坐标系：+Y 向上，正面朝 +Z；原点位于底面中心，模型最低点 y=0（保证可直接落地）。
- 整体尺寸不超过 3.0m(X) × 2.6m(Y) × 2.6m(Z)；两台设备比例不同，不要做成同一模型换色。
- GLB 2.0 单文件，材质与贴图全部内嵌，不引用外部 .bin/.png；三角形 3k~20k；单文件 ≤ 2MB；无需动画。

## 3. 制作方式

- 允许 pip 安装 trimesh（网络可用）后用图元/布尔拼装并导出 GLB；也可手写 glTF JSON + 二进制缓冲生成 GLB。不得使用需要登录/联网下载素材的付费资源。
- 必须用 trimesh.load 或 GLTF 解析器复核：文件可解析、mesh 数量、三角面数、包围盒尺寸。
- 必须用项目自带的 three.js（static/vendor/three）实际加载预览并截图，确认材质、朝向、落地正确。

## 4. 预览与自测

在项目根起一个临时静态服务（例如 python -m http.server 8010，工作目录为项目根），把预览页放在 output/playwright/model-preview.html，通过 http://127.0.0.1:8010/output/playwright/model-preview.html 打开，用 importmap 指向 /static/vendor/three/build/three.module.js 与 /static/vendor/three/examples/jsm/。用 Playwright（.local-tools/node_modules/playwright，channel:'msedge'）截图：

- output/playwright/model-preview-cnc.png
- output/playwright/model-preview-pump.png

预览页需展示：模型正 3/4 视角、地面网格、坐标轴，便于确认朝向与落地。截图后关闭 8010 端口临时服务。

## 5. 边界

- 只允许写 static/uploads/device_models/ 下两个新 GLB，以及 output/playwright/ 下预览页与截图、.local-tools/ 下临时脚本。
- 不得修改 config.json、api_server.py、static/index.html、equipment.html、equipment-scene.js。
- 不得重启 8000 端口上的服务；不得删除或覆盖已有模型文件。

## 6. 交付报告

报告需包含：两个文件的绝对/相对路径与字节数、包围盒尺寸（m）、三角面数、mesh 数、`trimesh.load` 校验输出摘要、预览截图路径、已知问题（若有）。
## 7. v2 追加模型（2026-11-09）

在原有 CNC 与泵组试验台之外，追加 4 个设备模型，均已登记为设备并接入数字孪生页：

| 设备 | id | 模型文件 | 三角面 | 包围盒 X×Y×Z (m) |
| --- | --- | --- | --- | --- |
| 六轴机械臂工作站 | device-robot-arm-01 | static/uploads/device_models/robotic_arm_cell.glb | 10,396 | 1.690×1.980×1.805 |
| 传送带线 | device-conveyor-01 | static/uploads/device_models/conveyor_line.glb | 2,676 | 2.989×1.056×0.986 |
| 配电控制柜 | device-cabinet-01 | static/uploads/device_models/electrical_cabinet.glb | 2,648 | 1.352×2.453×0.728 |
| 工业冷却风机 | device-fan-01 | static/uploads/device_models/cooling_fan.glb | 10,280 | 1.320×2.000×0.850 |

制作脚本：.local-tools/build_more_device_models.py；预览页：output/playwright/model-preview-more.html；
预览脚本：.local-tools/preview_more.mjs（4/4 PASS）；截图：output/playwright/model-preview-robot.png、model-preview-conveyor.png、model-preview-cabinet.png、model-preview-fan.png。

新模型均满足 §2 坐标与尺寸规范，模型最低点 y=0，材质内嵌，单文件 ≤ 2MB。设备登记通过 POST /api/settings 写入 config.json 与 MySQL，selected_device_id 保持不变。
