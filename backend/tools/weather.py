import json
import http.client
import urllib.parse
from typing import Dict, Any
from .base import Tool, tool_registry


def _geocode(city: str) -> tuple:
    """通过 Open-Meteo Geocoding API 将城市名转为经纬度"""
    conn = http.client.HTTPSConnection("geocoding-api.open-meteo.com", timeout=10)
    params = urllib.parse.urlencode({"name": city, "count": 1, "language": "zh"})
    conn.request("GET", f"/v1/search?{params}")
    resp = conn.getresponse()
    data = json.loads(resp.read().decode("utf-8"))
    conn.close()

    if resp.status != 200 or not data.get("results"):
        raise ValueError(f"未找到城市「{city}」的坐标信息，请检查城市名称")

    result = data["results"][0]
    return result["latitude"], result["longitude"], result.get("country", ""), result.get("admin1", "")


class WeatherTool(Tool):
    name = "weather"
    description = "用于查询指定城市或地点的天气信息"
    parameters = {
        "city": {
            "type": "string",
            "description": "城市或地点名称，例如：北京、东京、纽约、伦敦、巴黎"
        }
    }

    def execute(self, **kwargs) -> str:
        city = kwargs.get("city", "")
        if not city:
            return "错误：请提供城市名称"

        try:
            lat, lon, country, region = _geocode(city)

            conn = http.client.HTTPSConnection("api.open-meteo.com", timeout=15)
            conn.request(
                "GET",
                f"/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&hourly=temperature_2m&daily=temperature_2m_max,temperature_2m_min&timezone=auto"
            )
            response = conn.getresponse()
            content = response.read().decode('utf-8')
            conn.close()

            if response.status != 200:
                return f"查询失败，状态码：{response.status}"

            data = json.loads(content)

            current = data.get("current", {})
            daily = data.get("daily", {})

            temp = current.get("temperature_2m", 0)
            humidity = current.get("relative_humidity_2m", 0)
            wind_speed = current.get("wind_speed_10m", 0)
            weather_code = current.get("weather_code", 0)

            max_temp = daily.get("temperature_2m_max", [0])[0]
            min_temp = daily.get("temperature_2m_min", [0])[0]

            weather_map = {
                0: "晴朗", 1: "多云", 2: "多云", 3: "阴天",
                45: "雾", 48: "雾",
                51: "毛毛雨", 53: "小雨", 55: "中雨",
                61: "小雨", 63: "中雨", 65: "大雨",
                71: "小雪", 73: "中雪", 75: "大雪",
                80: "阵雨", 81: "阵雨", 82: "雷阵雨"
            }
            weather_desc = weather_map.get(weather_code, "未知")

            location = f"{city}"
            if region:
                location += f"（{region}，{country}" if country else f"（{region}"
            elif country:
                location += f"（{country}"
            if region or country:
                location += "）"

            return (
                f"{location}天气信息：\n"
                f"天气状况：{weather_desc}\n"
                f"当前温度：{temp}°C\n"
                f"今日最高：{max_temp}°C\n"
                f"今日最低：{min_temp}°C\n"
                f"湿度：{humidity}%\n"
                f"风速：{wind_speed} km/h"
            )

        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"天气查询错误：{str(e)}"


tool_registry.register(WeatherTool())