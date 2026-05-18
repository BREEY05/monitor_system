import json
import time
from datetime import datetime
from pathlib import Path

import board
import adafruit_dht
import requests
from gpiozero import DigitalInputDevice


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
DEFAULT_CONFIG = {
    "server_url": "http://127.0.0.1:8000",
    "device_id": "raspberry-pi-5",
    "area": "A区",
    "interval_seconds": 5,
    "dht11_gpio": 4,
    "sw420_gpio": 17,
    "sw420_sample_seconds": 1.0,
}

GPIO_TO_BOARD = {
    2: board.D2,
    3: board.D3,
    4: board.D4,
    5: board.D5,
    6: board.D6,
    9: board.D9,
    10: board.D10,
    11: board.D11,
    13: board.D13,
    17: board.D17,
    19: board.D19,
    22: board.D22,
    26: board.D26,
    27: board.D27,
}


def load_config():
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            user_config = json.load(f)
        return {**DEFAULT_CONFIG, **user_config}
    return DEFAULT_CONFIG.copy()


def read_vibration(sensor, sample_seconds):
    end_time = time.time() + float(sample_seconds)
    pulses = 0
    last_value = sensor.value
    while time.time() < end_time:
        current = sensor.value
        if current and not last_value:
            pulses += 1
        last_value = current
        time.sleep(0.005)
    return pulses


def main():
    config = load_config()
    dht_pin = GPIO_TO_BOARD.get(int(config["dht11_gpio"]))
    if not dht_pin:
        raise RuntimeError(f"Unsupported DHT11 GPIO: {config['dht11_gpio']}")

    dht = adafruit_dht.DHT11(dht_pin)
    vibration = DigitalInputDevice(int(config["sw420_gpio"]), pull_up=False)
    endpoint = config["server_url"].rstrip("/") + "/api/raspberry/sensors"

    print(f"Posting sensor data to {endpoint}")
    while True:
        payload = {
            "device_id": config["device_id"],
            "area": config["area"],
            "timestamp": datetime.now().isoformat(),
        }
        try:
            payload["temperature"] = float(dht.temperature)
            payload["humidity"] = float(dht.humidity)
        except RuntimeError as exc:
            print(f"DHT11 read skipped: {exc}")

        payload["vibration"] = read_vibration(vibration, config["sw420_sample_seconds"])

        try:
            response = requests.post(endpoint, json=payload, timeout=8)
            response.raise_for_status()
            print(f"{payload['timestamp']} uploaded: {payload}")
        except requests.RequestException as exc:
            print(f"Upload failed: {exc}")

        time.sleep(float(config["interval_seconds"]))


if __name__ == "__main__":
    main()
