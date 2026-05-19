import time
from datetime import datetime

import requests


# Only edit these values.
SERVER_URL = "http://192.168.43.105:8000"
DEVICE_ID = "raspberry-pi-5"
AREA = "A区"
DHT11_GPIO = 4
SW420_GPIO = 17
INTERVAL_SECONDS = 1
HTTP_TIMEOUT_SECONDS = 1.5


try:
    import adafruit_dht
    import board
    from gpiozero import InputDevice
    SENSOR_AVAILABLE = True
except Exception as exc:
    SENSOR_AVAILABLE = False
    print(f"[SENSOR] sensor libraries unavailable: {exc}")


def board_pin(gpio):
    return getattr(board, f"D{gpio}")


def init_sensors():
    if not SENSOR_AVAILABLE:
        raise RuntimeError("Sensor libraries are not available")
    dht = adafruit_dht.DHT11(board_pin(DHT11_GPIO))
    vibration = InputDevice(SW420_GPIO)
    print(f"[SENSOR] DHT11 GPIO{DHT11_GPIO}, SW-420 GPIO{SW420_GPIO} initialized")
    return dht, vibration


def read_sensor_data(dht, vibration):
    data = {
        "device_id": DEVICE_ID,
        "area": AREA,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "temperature": None,
        "humidity": None,
        "vibration": 1 if vibration.value else 0,
    }

    try:
        data["temperature"] = dht.temperature
        data["humidity"] = dht.humidity
    except RuntimeError as exc:
        print(f"[DHT11] read failed this round: {exc}")

    return data


def upload(data):
    endpoint = SERVER_URL.rstrip("/") + "/api/raspberry/sensors"
    payload = {k: v for k, v in data.items() if v is not None}
    response = requests.post(endpoint, json=payload, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()


def print_line(data, ok, error=""):
    temp = "--" if data["temperature"] is None else f"{data['temperature']:.1f}C"
    hum = "--" if data["humidity"] is None else f"{data['humidity']:.1f}%"
    vib = "shake" if data["vibration"] else "still"
    status = "sent" if ok else f"send failed: {error}"
    print(f"[{data['timestamp']}] temp={temp} humidity={hum} sw420={vib} -> {status}")


def main():
    dht, vibration = init_sensors()
    print(f"[UPLOAD] {SERVER_URL.rstrip()}/api/raspberry/sensors")
    while True:
        data = read_sensor_data(dht, vibration)
        try:
            upload(data)
            print_line(data, True)
        except Exception as exc:
            print_line(data, False, str(exc))
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
