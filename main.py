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
    try:
        # Se houver um arquivo antigo, remove para não dar conflito
        if os.path.exists("downloaded_audio.mp3"):
            os.remove("downloaded_audio.mp3")

        ydl_opts = {
            # Baixa QUALQUER melhor áudio disponível (não importa se é webm ou m4a)
            'format': 'bestaudio/best',
            
            # Usa o FFmpeg (instalado no Docker) para converter tudo para MP3
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            
            # Nome fixo para facilitar o envio (o yt-dlp vai adicionar .mp3 automaticamente)
            'outtmpl': 'downloaded_audio', 
            
            # Configurações de autenticação e "disfarce"
            'cookiefile': 'cookies.txt',
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'noplaylist': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            titulo_original = info.get('title', 'audio') + ".mp3"

        # O arquivo final será .mp3 por causa do postprocessor
        filename = "downloaded_audio.mp3"

        return FileResponse(path=filename, filename=titulo_original, media_type='audio/mpeg')

    except Exception as e:
        # Mostra o erro real na tela se falhar
        return HTTPException(status_code=500, detail=str(e))
