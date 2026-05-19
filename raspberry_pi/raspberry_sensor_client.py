import time
from datetime import datetime

import requests


# ===== 修改这里即可 =====
SERVER_URL = "http://YOUR_HOST_IP:8000"
DEVICE_ID = "raspberry-pi-5"
AREA = "A区"
DHT11_GPIO = 4
SW420_GPIO = 17
INTERVAL_SECONDS = 1
# =======================


try:
    import board
    import adafruit_dht
    from gpiozero import InputDevice
    SENSOR_AVAILABLE = True
except Exception as exc:
    SENSOR_AVAILABLE = False
    print(f"[SENSOR] 传感器库不可用: {exc}")


def dht_pin_from_gpio(gpio):
    name = f"D{gpio}"
    if not hasattr(board, name):
        raise RuntimeError(f"board.{name} 不存在，请检查 DHT11_GPIO")
    return getattr(board, name)


def init_sensors():
    if not SENSOR_AVAILABLE:
        return None, None
    dht = adafruit_dht.DHT11(dht_pin_from_gpio(DHT11_GPIO))
    vibration = InputDevice(SW420_GPIO)
    print(f"[SENSOR] DHT11 GPIO{DHT11_GPIO}, SW-420 GPIO{SW420_GPIO} 已初始化")
    return dht, vibration


def read_sensors(dht, vibration):
    data = {
        "device_id": DEVICE_ID,
        "area": AREA,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "temperature": None,
        "humidity": None,
        "vibration": 0,
    }

    if dht:
        try:
            data["temperature"] = dht.temperature
            data["humidity"] = dht.humidity
        except RuntimeError as exc:
            print(f"[DHT11] 本次读取失败，跳过温湿度: {exc}")

    if vibration:
        data["vibration"] = 1 if vibration.value else 0

    return data


def print_data(data, uploaded, error=None):
    temp = "--" if data["temperature"] is None else f"{data['temperature']:.1f}C"
    hum = "--" if data["humidity"] is None else f"{data['humidity']:.1f}%"
    vib = "震动" if data["vibration"] else "静止"
    status = "已上传" if uploaded else f"上传失败: {error}"
    print(f"[{data['timestamp']}] 温度={temp} 湿度={hum} SW-420={vib} -> {status}")


def upload(data):
    endpoint = SERVER_URL.rstrip("/") + "/api/raspberry/sensors"
    payload = {key: value for key, value in data.items() if value is not None}
    response = requests.post(endpoint, json=payload, timeout=5)
    response.raise_for_status()


def main():
    dht, vibration = init_sensors()
    print(f"[UPLOAD] {SERVER_URL.rstrip()}/api/raspberry/sensors")
    while True:
        data = read_sensors(dht, vibration)
        try:
            upload(data)
            print_data(data, True)
        except Exception as exc:
            print_data(data, False, exc)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
