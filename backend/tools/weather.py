import urllib.parse
import json
import http.client
from typing import Dict, Any
from .base import Tool, tool_registry

CITY_COORDS = {
    "北京": {"latitude": 39.9042, "longitude": 116.4074},
    "上海": {"latitude": 31.2304, "longitude": 121.4737},
    "广州": {"latitude": 23.1291, "longitude": 113.2644},
    "深圳": {"latitude": 22.5431, "longitude": 114.0579},
    "杭州": {"latitude": 30.2741, "longitude": 120.1551},
    "南京": {"latitude": 32.0603, "longitude": 118.7969},
    "成都": {"latitude": 30.5728, "longitude": 104.0668},
    "武汉": {"latitude": 30.5928, "longitude": 114.3055},
    "西安": {"latitude": 34.3416, "longitude": 108.9398},
    "重庆": {"latitude": 29.4316, "longitude": 106.9123},
    "天津": {"latitude": 39.0842, "longitude": 117.2009},
    "苏州": {"latitude": 31.2990, "longitude": 120.5853},
    "郑州": {"latitude": 34.7466, "longitude": 113.6253},
    "长沙": {"latitude": 28.2280, "longitude": 112.9388},
    "东莞": {"latitude": 23.0205, "longitude": 113.7512},
}


class WeatherTool(Tool):
    name = "weather"
    description = "用于查询指定城市的天气信息"
    parameters = {
        "city": {
            "type": "string",
            "description": "城市名称，支持：北京、上海、广州、深圳、杭州、南京、成都、武汉、西安、重庆、天津、苏州、郑州、长沙、东莞"
        }
    }

    def execute(self, **kwargs) -> str:
        city = kwargs.get("city", "")
        if not city:
            return "错误：请提供城市名称"

        coords = CITY_COORDS.get(city)
        if not coords:
            return f"暂不支持查询{city}的天气，当前支持的城市：{', '.join(CITY_COORDS.keys())}"

        try:
            lat = coords["latitude"]
            lon = coords["longitude"]
            
            conn = http.client.HTTPSConnection("api.open-meteo.com", timeout=15)
            conn.request(
                "GET",
                f"/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&hourly=temperature_2m&daily=temperature_2m_max,temperature_2m_min&timezone=Asia/Shanghai"
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
            
            return (
                f"{city}天气信息：\n"
                f"天气状况：{weather_desc}\n"
                f"当前温度：{temp}°C\n"
                f"今日最高：{max_temp}°C\n"
                f"今日最低：{min_temp}°C\n"
                f"湿度：{humidity}%\n"
                f"风速：{wind_speed} km/h"
            )

        except Exception as e:
            return f"天气查询错误：{str(e)}"


tool_registry.register(WeatherTool())