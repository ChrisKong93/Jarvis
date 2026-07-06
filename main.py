from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import http.client
import json

app = FastAPI()

LLAMA_CPP_URL = "http://192.168.0.201:8082"

templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


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
        
        return result
    finally:
        conn.close()


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=300)
