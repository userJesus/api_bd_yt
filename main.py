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
            # 1. FORÇA APENAS ÁUDIO LEVE (M4A)
            # Isso evita baixar 9GB. Vai baixar cerca de 300MB para 5 horas.
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio',
            
            # 2. CONFIGURAÇÕES DE REDE E RETRIES (Para não falhar em vídeo longo)
            'socket_timeout': 15,         # Tempo limite de conexão
            'retries': 10,                # Tenta 10 vezes se o vídeo falhar
            'fragment_retries': 10,       # Tenta 10 vezes se um pedacinho falhar
            'skip_unavailable_fragments': False, # Não pula pedaços (evita áudio corrompido)
            
            # 3. OTIMIZAÇÃO DE DISCO (Evita erro de rename/no such file)
            'keepvideo': False,
            'buffer_size': 1024,          # Buffer menor para economizar RAM
            'http_chunk_size': 10485760,  # Baixa em blocos de 10MB
            
            # 4. PÓS-PROCESSAMENTO (Garante MP3 no final)
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128', # 128kbps é suficiente para voz/youtube e muito mais leve/rápido
            }],
            
            # Configurações padrão
            'outtmpl': 'downloaded_audio', 
            'noplaylist': True,
            'cookiefile': 'cookies.txt',
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
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
