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

        # Configuração otimizada para vídeos longos (Podcast/Lives)
        ydl_opts = {
            # 1. FORÇA APENAS ÁUDIO LEVE (AAC/M4A)
            # Evita baixar arquivos de vídeo de 9GB. Baixa direto o áudio (~60MB por hora).
            'format': 'bestaudio[ext=m4a]/bestaudio',
            
            # 2. RESILIÊNCIA DE REDE (Para não falhar em 5 horas de download)
            'socket_timeout': 30,         # Aumenta tolerância de conexão
            'retries': 20,                # Tenta 20 vezes se falhar o vídeo
            'fragment_retries': 20,       # Tenta 20 vezes se falhar um pedacinho
            'skip_unavailable_fragments': False, # Não pula pedaços (evita áudio picotado)
            
            # 3. OTIMIZAÇÃO DE DISCO E MEMÓRIA
            'keepvideo': False,
            'buffer_size': 1024 * 1024,   # Buffer de 1MB para economizar RAM
            'http_chunk_size': 10485760,  # Baixa em blocos de 10MB
            
            # 4. CONVERSÃO FINAL (Garante MP3 compatível)
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128', # 128kbps é o padrão do YouTube, mais rápido de processar
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
