import fcntl
import json
from time import time

from appearance import STATE
from weather import weather

CITY_FILE = STATE / "weather-city"
CACHE_FILE = STATE / "island-weather.json"


def saved_city():
    try:
        return CITY_FILE.read_text().strip()
    except OSError:
        return ""


def cached_weather():
    try:
        data = json.loads(CACHE_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_atomic(path, text):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def update_weather(city=None):
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "weather.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        name = city or saved_city()
        if not name:
            return None
        current = cached_weather()
        if (city is None and current.get("city") == name and current.get("data")
                and time() - current.get("updated", 0) < 840):
            return current["data"]
        data = weather(name)
        write_atomic(CACHE_FILE, json.dumps({"city": name, "updated": time(), "data": data}))
        if city is not None:
            write_atomic(CITY_FILE, name + "\n")
        return data


if __name__ == "__main__":
    update_weather()
