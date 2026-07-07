from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import http.client
import json

from session_manager import session_manager
from context_manager import truncate_messages, calculate_messages_tokens
from backend.memory import memory_manager

app = FastAPI()

LLAMA_CPP_URL = "http://192.168.0.201:8081"

from backend.agent import Agent
agent = Agent(llama_cpp_url=LLAMA_CPP_URL)

templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/session")
async def create_session():
    session_id = session_manager.create_session()
    return {"session_id": session_id}


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    session = session_manager.get_session(session_id)
    if session:
        return {
            "session_id": session.session_id,
            "messages": session.messages,
            "created_at": session.created_at.isoformat(),
            "last_active": session.last_active.isoformat()
        }
    return {"error": "会话不存在"}


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    success = session_manager.delete_session(session_id)
    return {"success": success}


def get_host_port():
    import urllib.parse
    parsed = urllib.parse.urlparse(LLAMA_CPP_URL)
    return parsed.hostname, parsed.port or 80


@app.post("/api/completions")
async def completions(request: Request):
    data = await request.json()
    
    host, port = get_host_port()
    conn = http.client.HTTPConnection(host, port, timeout=300)
    
    try:
        conn.request('POST', '/completion', json.dumps(data), {'Content-Type': 'application/json'})
        response = conn.getresponse()
        content = response.read().decode('utf-8')
        return json.loads(content)
    finally:
        conn.close()


@app.post("/api/chat")
async def chat(request: Request):
    data = await request.json()
    
    import time
    start_time = time.time()
    
    messages = data.get('messages', [])
    max_tokens = data.get('max_tokens', 2048)
    
    truncated_messages = truncate_messages(messages, max_tokens)
    data['messages'] = truncated_messages
    
    host, port = get_host_port()
    conn = http.client.HTTPConnection(host, port, timeout=300)
    
    try:
        conn.request('POST', '/chat/completions', json.dumps(data), {'Content-Type': 'application/json'})
        response = conn.getresponse()
        content = response.read().decode('utf-8')
        elapsed_time = time.time() - start_time
        result = json.loads(content)
        
        if 'usage' in result and 'completion_tokens' in result['usage']:
            completion_tokens = result['usage']['completion_tokens']
            tokens_per_second = round(completion_tokens / elapsed_time, 2) if elapsed_time > 0 else 0
            result['tokens_per_second'] = tokens_per_second
            result['response_time'] = round(elapsed_time, 2)
        
        result['context_tokens'] = calculate_messages_tokens(truncated_messages)
        result['original_messages_count'] = len(messages)
        result['truncated_messages_count'] = len(truncated_messages)
        
        return result
    finally:
        conn.close()


@app.post("/api/agent")
async def agent_chat(request: Request):
    data = await request.json()
    
    import time
    start_time = time.time()
    
    messages = data.get('messages', [])
    max_tokens = data.get('max_tokens', 2048)
    
    result = agent.run(messages, max_tokens)
    elapsed_time = time.time() - start_time
    
    result['response_time'] = round(elapsed_time, 2)
    
    return result


@app.get("/api/tools")
async def get_tools():
    from backend.tools.base import tool_registry
    return {"tools": tool_registry.get_tools_list()}


@app.get("/api/models")
async def models():
    host, port = get_host_port()
    conn = http.client.HTTPConnection(host, port, timeout=30)
    
    try:
        conn.request('GET', '/models')
        response = conn.getresponse()
        content = response.read().decode('utf-8')
        return json.loads(content)
    except:
        return {"error": "无法连接到llama.cpp服务器"}
    finally:
        conn.close()


@app.get("/api/health")
async def health():
    host, port = get_host_port()
    conn = http.client.HTTPConnection(host, port, timeout=30)
    
    try:
        conn.request('GET', '/health')
        response = conn.getresponse()
        content = response.read().decode('utf-8')
        return {"status": "ok", "llama_cpp": json.loads(content)}
    except:
        return {"status": "error", "message": "无法连接到llama.cpp服务器"}
    finally:
        conn.close()


@app.get("/api/memory/stats")
async def get_memory_stats():
    return memory_manager.get_stats()


@app.get("/api/memory")
async def get_all_memories():
    return memory_manager.get_all_memories()


@app.post("/api/memory")
async def add_memory(request: Request):
    data = await request.json()
    content = data.get('content', '')
    category = data.get('category', 'general')
    metadata = data.get('metadata', {})
    
    if not content:
        return {"error": "内容不能为空"}
    
    memory_id = memory_manager.add_long_term_memory(content, category, metadata)
    return {"memory_id": memory_id}


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str):
    success = memory_manager.long_term.delete_memory(memory_id)
    return {"success": success}


@app.get("/api/memory/search")
async def search_memories(query: str, top_k: int = 5):
    results = memory_manager.retrieve_relevant_memories(query, top_k)
    return {"results": results}


@app.delete("/api/memory")
async def clear_all_memories():
    memory_manager.clear_all()
    return {"success": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=300)
