# 树莓派传感器上传脚本

树莓派端只需要运行一个文件：

```bash
python3 raspberry_sensor_client.py
```

它会每 1 秒读取一次：

- DHT11：温度、湿度
- SW-420：是否震动

同时在终端打印，并上传到主机：

```text
POST /api/raspberry/sensors
```

## 安装依赖

```bash
cd raspberry_pi
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 修改主机地址

打开 `raspberry_sensor_client.py`，只改顶部这几行：

```python
SERVER_URL = "http://YOUR_HOST_IP:8000"
DEVICE_ID = "raspberry-pi-5"
AREA = "A区"
DHT11_GPIO = 4
SW420_GPIO = 17
INTERVAL_SECONDS = 1
```

例如主机 IP 是 `192.168.1.20`：

```python
SERVER_URL = "http://192.168.1.20:8000"
```

## 接线默认值

- DHT11 data：BCM GPIO 4
- SW-420 DO：BCM GPIO 17
- 电源：3.3V
- GND：GND

## 终端输出示例

```text
[2026-05-19T10:30:01] 温度=25.0C 湿度=56.0% SW-420=静止 -> 已上传
```
