"""
语音交互路由（可选增强）。

提供服务器端的语音识别（STT）和语音合成（TTS）API。
当前实现使用 OpenAI Whisper API（STT）和 edge-tts（TTS）。

依赖安装：
  pip install openai edge-tts

注意：这些路由是可选的增强功能。
前端默认使用浏览器原生 Web Speech API 进行语音交互，
只有在配置了相关 API Key 后才会使用后端服务。
"""

import io
import logging
import os

from typing import Optional

from fastapi import Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)


def register_voice_routes(app, get_current_user):
    """注册语音相关路由。"""

    @app.post("/api/voice/stt")
    async def speech_to_text(
        request: Request,
        audio: UploadFile = File(...),
        provider: str = Form("whisper_api"),
        user: dict = Depends(get_current_user),
    ):
        """语音识别：将音频转为文字。

        支持的 provider:
          - whisper_api: OpenAI Whisper API（需设置 OPENAI_API_KEY 环境变量）
          - browser: 返回提示，让前端使用浏览器 API
        """
        if provider == "browser":
            return JSONResponse({
                "text": "",
                "note": "请使用浏览器内置语音识别功能",
                "provider": "browser",
            })

        if provider == "whisper_api":
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                return JSONResponse(
                    {"error": "未配置 OpenAI API Key，请在环境变量中设置 OPENAI_API_KEY"},
                    status_code=400,
                )

            try:
                import openai

                audio_data = await audio.read()
                client = openai.OpenAI(api_key=api_key)

                # 将音频数据包装为类文件对象
                audio_file = io.BytesIO(audio_data)
                audio_file.name = audio.filename or "recording.webm"

                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="zh",
                )

                return JSONResponse({
                    "text": transcript.text,
                    "language": "zh",
                    "provider": "whisper_api",
                })

            except ImportError:
                return JSONResponse(
                    {"error": "openai 库未安装，请执行: pip install openai"},
                    status_code=500,
                )
            except Exception as e:
                logger.exception("Whisper API 调用失败")
                return JSONResponse(
                    {"error": f"语音识别失败: {str(e)}"},
                    status_code=500,
                )

        return JSONResponse(
            {"error": f"不支持的 STT provider: {provider}"},
            status_code=400,
        )

    @app.post("/api/voice/tts")
    async def text_to_speech(
        request: Request,
        user: dict = Depends(get_current_user),
    ):
        """语音合成：将文字转为音频。

        请求体: { "text": "...", "voice": "zh-CN-XiaoxiaoNeural", "speed": 1.0 }

        使用 edge-tts（免费、高质量、支持中文多种语音角色）。
        """
        try:
            import edge_tts
        except ImportError:
            return JSONResponse(
                {"error": "edge-tts 库未安装，请执行: pip install edge-tts"},
                status_code=500,
            )

        data = await request.json()
        text = data.get("text", "").strip()
        if not text:
            return JSONResponse({"error": "文本不能为空"}, status_code=400)

        voice = data.get("voice", "zh-CN-XiaoxiaoNeural")
        speed = data.get("speed", 1.0)

        # edge-tts 的语速参数格式：+0% ~ +100%，-0% ~ -50%
        rate_str = f"+{int((speed - 1.0) * 100)}%" if speed >= 1.0 else f"-{int((1.0 - speed) * 50)}%"

        try:
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate_str)
            audio_data = io.BytesIO()

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.write(chunk["data"])

            audio_data.seek(0)

            return StreamingResponse(
                audio_data,
                media_type="audio/mpeg",
                headers={
                    "Content-Disposition": f'inline; filename="speech.mp3"',
                    "Content-Length": str(audio_data.getbuffer().nbytes),
                },
            )

        except ValueError as e:
            return JSONResponse(
                {"error": f"语音参数错误: {str(e)}"},
                status_code=400,
            )
        except Exception as e:
            logger.exception("TTS 生成失败")
            return JSONResponse(
                {"error": f"语音合成失败: {str(e)}"},
                status_code=500,
            )

    @app.get("/api/voice/voices")
    async def list_voices(user: dict = Depends(get_current_user)):
        """列出可用的 TTS 语音角色。"""
        try:
            import edge_tts

            voices = await edge_tts.list_voices()
            zh_voices = [
                {
                    "name": v["ShortName"],
                    "display_name": v["DisplayName"],
                    "gender": v.get("Gender", ""),
                    "locale": v.get("Locale", ""),
                }
                for v in voices
                if v.get("Locale", "").startswith("zh")
            ]
            return {"voices": zh_voices, "total": len(zh_voices)}
        except ImportError:
            return {"error": "edge-tts 未安装", "voices": []}
        except Exception as e:
            logger.exception("获取语音列表失败")
            return {"error": str(e), "voices": []}
