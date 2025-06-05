# gpt4o_realtime_ws.py

import asyncio
import websockets
import base64
import json
import os
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

async def gpt4o_realtime_audio_stream(audio_generator):
    uri = "wss://api.openai.com/v1/audio/ws"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }

    async with websockets.connect(uri, extra_headers=headers, ping_interval=None) as websocket:
        # Send config message to OpenAI
        await websocket.send(json.dumps({
            "model": "gpt-4o-realtime-preview-2025-06-03",
            "audio": {
                "encoding": "mp3",
                "sample_rate": 24000,
            },
            "text": {"return_as_text": True},
        }))

        async def send_audio():
            async for chunk in audio_generator:
                await websocket.send(chunk)
            await websocket.send("[DONE]")

        async def receive_audio():
            async for message in websocket:
                if isinstance(message, bytes):
                    yield {"type": "audio", "audio": message}
                else:
                    msg = json.loads(message)
                    if "text" in msg:
                        yield {"type": "text", "text": msg["text"]}
                    if msg.get("type") == "tool_use":
                        yield {"type": "tool_use", "data": msg}

        await asyncio.gather(send_audio(), receive_audio())

# Example usage
# You'll integrate this with FastAPI or a frontend WebSocket endpoint

# For a FastAPI WebSocket route, you can:
# - Accept audio chunks from frontend
# - Feed to `gpt4o_realtime_audio_stream`
# - Yield audio + text back to frontend in real-time
