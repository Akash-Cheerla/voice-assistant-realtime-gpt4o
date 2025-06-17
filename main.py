import os
import base64
import tempfile
import traceback
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import OpenAI
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

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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

# Serve static files
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
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en",
                response_format="json",
                temperature=0.2,
                prompt="You are transcribing speech for a business form. "
                       "The user may say business names, postal codes, emails, and names. "
                       "Avoid guessing – transcribe phonetically when unclear."
            )
        user_text = result.text.strip()
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

@app.post("/upload-signature")
async def upload_signature(request: Request):
    try:
        body = await request.json()
        image_data = body.get("signature_image", "")
        if image_data.startswith("data:image/png;base64,"):
            image_data = image_data.split(",", 1)[1]
        with open("saved_signature.png", "wb") as f:
            f.write(base64.b64decode(image_data))
        print("✅ Signature image saved as saved_signature.png")
        return JSONResponse({"status": "signature saved"})
    except Exception as e:
        print("❌ Signature upload error:", e)
        return JSONResponse({"error": "Failed to save signature"}, status_code=500)

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
