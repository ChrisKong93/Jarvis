from fastapi import Depends, Request

from backend.memory import memory_manager


def register_memory_routes(app, get_current_user):
    @app.get("/api/memory/stats")
    async def get_memory_stats(user: dict = Depends(get_current_user)):
        if not user:
            return {"short_term_summaries": 0, "long_term_memories": 0}
        return memory_manager.get_stats(user["id"])

    @app.get("/api/memory")
    async def get_all_memories(user: dict = Depends(get_current_user)):
        if not user:
            return {"short_term": [], "long_term": []}
        return memory_manager.get_all_memories(user["id"])

    @app.post("/api/memory")
    async def add_memory(request: Request, user: dict = Depends(get_current_user)):
        if not user:
            return {"error": "未登录"}, 401
        data = await request.json()
        content = data.get("content", "")
        category = data.get("category", "general")
        metadata = data.get("metadata", {})

        if not content:
            return {"error": "内容不能为空"}

        memory_id = memory_manager.add_long_term_memory(user["id"], content, category, metadata)
        return {"memory_id": memory_id}

    @app.delete("/api/memory/{memory_id}")
    async def delete_memory(memory_id: str, user: dict = Depends(get_current_user)):
        if not user:
            return {"error": "未登录"}, 401
        from backend.memory.long_term import LongTermMemory
        long = LongTermMemory(user["id"])
        success = long.delete_memory(memory_id)
        return {"success": success}

    @app.get("/api/memory/search")
    async def search_memories(query: str, top_k: int = 5, user: dict = Depends(get_current_user)):
        if not user:
            return {"results": []}
        results = memory_manager.retrieve_relevant_memories(user["id"], query, top_k)
        return {"results": results}

    @app.delete("/api/memory")
    async def clear_all_memories(user: dict = Depends(get_current_user)):
        if not user:
            return {"error": "未登录"}, 401
        memory_manager.clear_all(user["id"])
        return {"success": True}
