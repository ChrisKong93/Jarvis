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
        self.local_knowledge = {
            "人工智能": {
                "title": "人工智能",
                "summary": "人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，旨在研究、开发用于模拟、延伸和扩展人的智能的理论、方法、技术及应用系统。人工智能领域的研究包括机器人、语言识别、图像识别、自然语言处理和专家系统等。",
                "topics": ["机器学习", "深度学习", "自然语言处理", "计算机视觉", "机器人"]
            },
            "机器学习": {
                "title": "机器学习",
                "summary": "机器学习是人工智能的核心技术，通过算法让计算机从数据中学习规律，从而做出预测或决策。机器学习算法可以分为监督学习、无监督学习和强化学习三大类。",
                "topics": ["监督学习", "无监督学习", "强化学习", "神经网络", "深度学习"]
            },
            "深度学习": {
                "title": "深度学习",
                "summary": "深度学习是机器学习的一个分支，使用多层神经网络来模拟人脑的学习过程。深度学习在图像识别、语音识别、自然语言处理等领域取得了突破性进展。",
                "topics": ["神经网络", "卷积神经网络", "循环神经网络", "Transformer"]
            },
            "北京": {
                "title": "北京",
                "summary": "北京是中华人民共和国的首都，是中国的政治、文化和国际交往中心。位于华北平原北部，拥有悠久的历史和丰富的文化遗产，如故宫、天坛、颐和园等。",
                "topics": ["故宫", "天安门", "长城", "颐和园", "鸟巢", "天坛"]
            },
            "上海": {
                "title": "上海",
                "summary": "上海是中国最大的城市和经济中心，位于长江入海口，是国际化的大都市。上海拥有外滩、东方明珠塔、南京路等著名景点。",
                "topics": ["外滩", "东方明珠", "南京路", "陆家嘴", "豫园"]
            },
            "广州": {
                "title": "广州",
                "summary": "广州是中国南方的经济中心和交通枢纽，位于珠江三角洲。广州是岭南文化的代表城市，拥有丰富的美食和历史文化遗产。",
                "topics": ["珠江", "广州塔", "白云山", "陈家祠", "沙面"]
            },
            "深圳": {
                "title": "深圳",
                "summary": "深圳是中国改革开放的窗口城市，位于珠江三角洲东岸。深圳是中国的科技之都，拥有众多高新技术企业。",
                "topics": ["深圳湾", "世界之窗", "欢乐谷", "腾讯", "华为"]
            },
            "天气": {
                "title": "天气",
                "summary": "天气是指某一地区在某一短时间内的大气状况，包括气温、湿度、降水、风向、风力等要素。天气预报是气象学的重要应用。",
                "topics": ["天气预报", "气象学", "气候", "自然灾害", "气候变化"]
            },
            "Python": {
                "title": "Python",
                "summary": "Python是一种高级、通用、解释型的编程语言，以其简洁的语法和强大的库生态系统而闻名。Python广泛应用于数据分析、人工智能、Web开发等领域。",
                "topics": ["数据分析", "Web开发", "人工智能", "自动化", "科学计算"]
            },
            "编程": {
                "title": "编程",
                "summary": "编程是指使用编程语言编写计算机程序的过程，是计算机科学的基础技能。编程可以解决各种实际问题，从简单的自动化脚本到复杂的软件系统。",
                "topics": ["算法", "数据结构", "软件工程", "代码", "调试"]
            },
            "历史": {
                "title": "历史",
                "summary": "历史是对人类过去事件的记录和研究，帮助我们理解现在和预测未来。中国拥有五千年的悠久历史，是世界上最古老的文明之一。",
                "topics": ["古代史", "近代史", "世界史", "中国史", "文明"]
            },
            "科学": {
                "title": "科学",
                "summary": "科学是通过观察、实验和推理来理解自然现象的系统方法。科学方法包括提出假设、进行实验、验证结果等步骤。",
                "topics": ["物理学", "化学", "生物学", "天文学", "数学"]
            },
            "技术": {
                "title": "技术",
                "summary": "技术是人类为了解决问题、改进生活而开发的工具、方法和技能。现代技术包括互联网、人工智能、生物技术、新能源等领域。",
                "topics": ["互联网", "人工智能", "生物技术", "新能源", "区块链"]
            },
            "经济": {
                "title": "经济",
                "summary": "经济学是研究资源配置和利用的社会科学。包括宏观经济学和微观经济学两大分支，涉及生产、分配、交换和消费等方面。",
                "topics": ["宏观经济", "微观经济", "金融", "市场", "贸易"]
            },
            "健康": {
                "title": "健康",
                "summary": "健康是指身体、心理和社会适应能力的良好状态。保持健康需要合理饮食、适量运动、良好的睡眠和积极的心态。",
                "topics": ["饮食", "运动", "睡眠", "心理健康", "养生"]
            },
            "教育": {
                "title": "教育",
                "summary": "教育是培养人的社会活动，包括学校教育、家庭教育和社会教育。教育的目的是促进个人全面发展和社会进步。",
                "topics": ["学校", "学习", "考试", "素质教育", "在线教育"]
            },
            "旅游": {
                "title": "旅游",
                "summary": "旅游是人们为了休闲、娱乐、商务等目的离开常住地前往其他地方的活动。旅游可以开阔眼界、放松身心、增长见识。",
                "topics": ["景点", "美食", "文化", "旅行", "攻略"]
            },
            "美食": {
                "title": "美食",
                "summary": "美食是指美味的食物，包括各种烹饪风格和地方特色菜肴。中国菜以其丰富多样和精湛技艺闻名世界。",
                "topics": ["中餐", "西餐", "川菜", "粤菜", "小吃"]
            },
            "电影": {
                "title": "电影",
                "summary": "电影是一种通过影像和声音来讲述故事的艺术形式。电影产业包括制片、发行、放映等环节，是重要的文化产业。",
                "topics": ["导演", "演员", "类型片", "票房", "影评"]
            },
            "音乐": {
                "title": "音乐",
                "summary": "音乐是通过声音来表达情感和思想的艺术形式。音乐包括古典音乐、流行音乐、民族音乐等多种类型。",
                "topics": ["歌曲", "乐器", "歌手", "流派", "演唱会"]
            },
            "新闻": {
                "title": "新闻",
                "summary": "新闻是指新近发生的、对公众有重要意义的事件报道。新闻媒体包括报纸、电视、广播和互联网等。",
                "topics": ["时事", "媒体", "报道", "资讯", "头条"]
            },
            "科技": {
                "title": "科技",
                "summary": "科技是科学技术的简称，是人类认识自然和改造自然的手段和方法。现代科技发展迅速，深刻改变了人们的生活方式。",
                "topics": ["创新", "发明", "研究", "技术", "科学"]
            },
            "文化": {
                "title": "文化",
                "summary": "文化是人类社会创造的物质财富和精神财富的总和，包括语言、艺术、宗教、习俗等。不同国家和民族有不同的文化特色。",
                "topics": ["艺术", "传统", "习俗", "语言", "节日"]
            },
            "体育": {
                "title": "体育",
                "summary": "体育是指以身体锻炼为手段的教育和竞赛活动，包括各种运动项目。体育可以增强体质、培养意志品质。",
                "topics": ["运动", "比赛", "健身", "奥林匹克", "足球"]
            },
            "娱乐": {
                "title": "娱乐",
                "summary": "娱乐是指人们在闲暇时间进行的消遣活动，包括电影、音乐、游戏、旅游等。娱乐可以放松身心、丰富生活。",
                "topics": ["游戏", "综艺", "演出", "休闲", "消遣"]
            }
        }

    def execute(self, **kwargs) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "错误：请提供搜索关键词"

        search_methods = [
            self._search_bing_cn_html,
            self._search_sogou,
            self._search_zhihu_html,
            self._search_local
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

    def _search_local(self, query: str) -> str:
        matched_topics = []
        
        for keyword, info in self.local_knowledge.items():
            if keyword in query or query in keyword:
                matched_topics.append(info)
                continue
            
            for topic in info.get("topics", []):
                if topic in query or query in topic:
                    matched_topics.append(info)
                    break

        if matched_topics:
            results = []
            for i, info in enumerate(matched_topics[:3], 1):
                results.append(f"{i}. {info['title']}")
                results.append(f"   {info['summary']}")
                if info.get("topics"):
                    results.append(f"   相关主题：{', '.join(info['topics'])}")
            
            return "本地知识库搜索结果：\n\n" + "\n\n".join(results)
        
        return "未找到相关搜索结果"


tool_registry.register(SearchTool())