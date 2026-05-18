# Raspberry Pi 5 Sensor Client

This folder contains the script that runs on Raspberry Pi 5 and uploads DHT11 and SW-420 readings to the host service every 5 seconds.

## Wiring

- DHT11 data pin: default BCM GPIO 4
- SW-420 digital output pin: default BCM GPIO 17
- Use 3.3V and GND from the Raspberry Pi.

## Install

```bash
cd raspberry_pi
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json
```

Edit `config.json` and set `server_url` to the host machine address, for example:

```json
{
  "server_url": "http://192.168.1.20:8000",
  "device_id": "raspberry-pi-5",
  "area": "A区",
  "interval_seconds": 5,
  "dht11_gpio": 4,
  "sw420_gpio": 17,
  "sw420_sample_seconds": 1.0
}
```

## Run

```bash
source .venv/bin/activate
python raspberry_sensor_client.py
```

The host receives data at:

```text
POST /api/raspberry/sensors
```

Each upload is written to the cloud database when PostgreSQL/Supabase is configured on the host.
