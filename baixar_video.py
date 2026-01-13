from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import yt_dlp
import os

app = FastAPI()

@app.get("/")
def home():
    return {"message": "API de Download do YouTube está online!"}

@app.get("/baixar")
def baixar_audio(url: str):
    """
    Exemplo de uso: /baixar?url=https://www.youtube.com/watch?v=VIDEO_ID
    """
    try:
        # Configuração para M4A (sem precisar do FFmpeg)
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio',
            'outtmpl': 'downloaded_audio.%(ext)s', # Nome fixo temporário para facilitar o envio
            'noplaylist': True
        }

        # Baixa o áudio
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = "downloaded_audio.m4a" # O nome que definimos no outtmpl
            titulo_original = info.get('title', 'audio') + ".m4a"

        # Retorna o arquivo para o usuário baixar
        # O filename='...' abaixo é o nome que aparecerá para o usuário
        return FileResponse(path=filename, filename=titulo_original, media_type='audio/mp4')

    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))

    # Nota: Em uma API real, você deve limpar o arquivo depois de enviar,
    # mas para este exemplo simples vamos manter assim.