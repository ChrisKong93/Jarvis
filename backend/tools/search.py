import urllib.parse
import json
import requests
from bs4 import BeautifulSoup
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

    def __init__(self):
        super().__init__()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0"
        }

    def execute(self, **kwargs) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "错误：请提供搜索关键词"

        search_methods = [
            self._search_bing_cn_html,
            self._search_sogou,
            self._search_zhihu_html
        ]

        for method in search_methods:
            try:
                result = method(query)
                if result and "搜索失败" not in result and "未找到" not in result:
                    return result
            except Exception:
                continue

        return "搜索失败，请稍后重试"

    def _search_bing_cn_html(self, query: str) -> str:
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://cn.bing.com/search?q={encoded_query}&count=5"
            
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                results = []
                
                for i, result in enumerate(soup.find_all('li', class_='b_algo')[:5], 1):
                    title_elem = result.find('h2')
                    url_elem = result.find('a')
                    snippet_elem = result.find('p')
                    
                    if title_elem and url_elem:
                        title = title_elem.get_text(strip=True)
                        link = url_elem.get('href', '')
                        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''
                        
                        if title:
                            results.append(f"{i}. {title}")
                            if snippet:
                                results.append(f"   {snippet[:150]}")
                            if link:
                                results.append(f"   链接：{link}")
                
                if results:
                    return "搜索结果：\n\n" + "\n\n".join(results)
            
            return "未找到相关搜索结果"
        except Exception:
            raise

    def _search_sogou(self, query: str) -> str:
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://www.sogou.com/web?query={encoded_query}&num=5"
            
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                results = []
                
                for i, result in enumerate(soup.find_all('div', class_='vrwrap')[:5], 1):
                    title_elem = result.find('h3')
                    url_elem = result.find('a')
                    content_elem = result.find('p', class_='content')
                    
                    if title_elem and url_elem:
                        title = title_elem.get_text(strip=True)
                        link = url_elem.get('href', '')
                        content = content_elem.get_text(strip=True) if content_elem else ''
                        
                        if title:
                            results.append(f"{i}. {title}")
                            if content:
                                results.append(f"   {content[:150]}")
                            if link:
                                results.append(f"   链接：{link}")
                
                if not results:
                    for i, result in enumerate(soup.find_all('h3', class_='title')[:5], 1):
                        url_elem = result.find('a')
                        if url_elem:
                            title = result.get_text(strip=True)
                            link = url_elem.get('href', '')
                            results.append(f"{i}. {title}")
                            if link:
                                results.append(f"   链接：{link}")
                
                if results:
                    return "搜索结果：\n\n" + "\n\n".join(results)
            
            return "未找到相关搜索结果"
        except Exception:
            raise

    def _search_zhihu_html(self, query: str) -> str:
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://www.zhihu.com/search?type=content&q={encoded_query}"
            
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                results = []
                
                for i, result in enumerate(soup.find_all('div', class_='SearchResult-Card')[:5], 1):
                    title_elem = result.find('h2')
                    content_elem = result.find('p')
                    url_elem = result.find('a')
                    
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        link = url_elem.get('href', '') if url_elem else ''
                        content = content_elem.get_text(strip=True)[:100] if content_elem else ''
                        
                        results.append(f"{i}. {title}")
                        if content:
                            results.append(f"   {content}")
                        if link and not link.startswith('/'):
                            results.append(f"   链接：{link}")
                        elif link:
                            results.append(f"   链接：https://www.zhihu.com{link}")
                
                if results:
                    return "知乎搜索结果：\n\n" + "\n\n".join(results)
            
            return "未找到相关搜索结果"
        except Exception:
            raise

    


tool_registry.register(SearchTool())