import json
from urllib.parse import urlencode
from urllib.request import urlopen


def weather_condition(code):
    if code == 0:
        return "☀", "晴"
    if code <= 3:
        return "☁", "多云"
    if code <= 48:
        return "≋", "雾"
    if code in (71, 73, 75, 77, 85, 86):
        return "❄", "雪"
    if code < 95:
        return "☂", "雨"
    return "ϟ", "雷暴"


def weather(city):
    def query(endpoint, **params):
        with urlopen(endpoint + "?" + urlencode(params), timeout=7) as response:
            return json.load(response)

    result = query("https://geocoding-api.open-meteo.com/v1/search", name=city, count=1, language="zh")
    places = result.get("results") or []
    if not places:
        raise ValueError("未找到城市，试试中英文全名。")
    place = places[0]
    result = query(
        "https://api.open-meteo.com/v1/forecast",
        latitude=place["latitude"], longitude=place["longitude"],
        current="temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,surface_pressure",
        daily="weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,uv_index_max,sunrise,sunset",
        forecast_days=5, timezone="auto",
    )
    return place, result["current"], result["daily"]


