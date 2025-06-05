import os
import base64
import tempfile
import traceback
from fastapi import FastAPI, UploadFile, File, Request, WebSocket
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from fill_pdf_logic import fill_pdf
from realtime_assistant import (
    process_transcribed_text,
    form_data,
    conversation_history,
    get_initial_assistant_message,
    end_triggered,
    reset_assistant_state
)
from gpt4o_realtime_ws import gpt4o_realtime_audio_stream
import openai

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
eleven_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

app = FastAPI()

# Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file mounting
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_index():
    return FileResponse("templates/index.html")

@app.get("/initial-message")
async def initial_message():
    assistant_text = get_initial_assistant_message()
    try:
        audio_reply = eleven_client.text_to_speech.convert(
            voice_id="EXAVITQu4vr4xnSDxMaL",
            model_id="eleven_monolingual_v1",
            text=assistant_text
        )
        audio_bytes = b"".join(audio_reply)
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    except Exception as e:
        print("🔊 ElevenLabs audio error:", e)
        audio_base64 = None

    return JSONResponse({
        "assistant_text": assistant_text,
        "assistant_audio_base64": audio_base64
    })

@app.post("/voice-stream")
async def voice_stream(audio: UploadFile = File(...)):
    if end_triggered:
        return JSONResponse({
            "user_text": "",
            "assistant_text": "END OF CONVERSATION",
            "audio_base64": None,
            "form_data": form_data
        })

    try:
        contents = await audio.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
            temp_audio.write(contents)
            temp_audio_path = temp_audio.name

        with open(temp_audio_path, "rb") as audio_file:
            result = openai.Audio.transcribe(
                model="whisper-1",
                file=audio_file,
                language="en"
            )

        user_text = result["text"].strip()
        print(f"🎤 USER SAID: {user_text}")

        assistant_text = await process_transcribed_text(user_text)
        print(f"🧠 ASSISTANT REPLY: {assistant_text}")

        try:
            audio_reply = eleven_client.text_to_speech.convert(
                voice_id="EXAVITQu4vr4xnSDxMaL",
                model_id="eleven_monolingual_v1",
                text=assistant_text
            )
            audio_bytes = b"".join(audio_reply)
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        except Exception as e:
            print("🎧 ElevenLabs speech error:", e)
            audio_base64 = None

        return JSONResponse({
            "user_text": user_text,
            "assistant_text": assistant_text,
            "audio_base64": audio_base64,
            "form_data": form_data
        })

    except Exception as e:
        print("❌ Error in /voice-stream:", e)
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

@app.websocket("/ws-gpt4o")
async def gpt4o_ws(websocket: WebSocket):
    await websocket.accept()

    async def audio_generator():
        while True:
            try:
                chunk = await websocket.receive_bytes()
                if chunk == b"[DONE]":
                    break
                yield chunk
            except:
                break

    try:
        async for result in gpt4o_realtime_audio_stream(audio_generator()):
            if result["type"] == "audio":
                await websocket.send_bytes(result["audio"])
            elif result["type"] == "text":
                await websocket.send_json({"text": result["text"]})
    except Exception as e:
        print("⚠️ GPT-4o stream failed:", e)
        await websocket.send_json({"error": str(e)})

@app.get("/form-data")
async def get_form_data():
    return JSONResponse(form_data)

@app.post("/confirm")
async def confirm(request: Request):
    try:
        body = await request.json()
        if body.get("confirmed"):
            edited_data = body.get("form_data", {})
            fill_pdf("form_template.pdf", "filled_form.pdf", edited_data)
            return JSONResponse({"status": "filled"})
        return JSONResponse({"status": "not confirmed"}, status_code=400)
    except Exception as e:
        print("❌ Error in /confirm:", e)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/download")
async def download_pdf():
    return FileResponse("filled_form.pdf", media_type="application/pdf", filename="MerchantForm.pdf")

@app.post("/reset")
async def reset():
    reset_assistant_state()
    return JSONResponse({"status": "reset successful"})
