import urllib.parse
import json
import requests
from typing import Dict, Any
from .base import Tool, tool_registry


class SearchTool(Tool):
    name = "search"
    description = "用于搜索互联网信息，获取最新的新闻、知识和数据"
    parameters = {
        "query": {
            "type": "string",
            "description": "搜索关键词，例如：人工智能最新进展"
        }
    }

    def execute(self, **kwargs) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "错误：请提供搜索关键词"

        try:
            encoded_query = urllib.parse.quote(query)
            
            url = f"https://zh.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&format=json&srlimit=5"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=15)

            if response.status_code != 200:
                return f"搜索失败，状态码：{response.status_code}"

            data = response.json()
            results = []
            
            if "query" in data and "search" in data["query"]:
                for i, item in enumerate(data["query"]["search"][:5], 1):
                    title = item.get("title", "")
                    snippet = item.get("snippet", "")
                    snippet = snippet.replace('<span class="searchmatch">', '').replace('</span>', '')
                    url = f"https://zh.wikipedia.org/wiki/{urllib.parse.quote(title)}"
                    results.append(f"{i}. {title}\n   {snippet}\n   链接：{url}")
            
            if results:
                return "搜索结果：\n\n" + "\n\n".join(results)
            else:
                return "未找到相关搜索结果，正在尝试英文搜索..."

        except requests.exceptions.RequestException as e:
            return f"搜索网络错误：{str(e)}"
        except json.JSONDecodeError as e:
            return f"搜索结果解析错误：{str(e)}"
        except Exception as e:
            return f"搜索错误：{str(e)}"


tool_registry.register(SearchTool())