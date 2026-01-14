from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import yt_dlp
import os
import glob
import math
import time

app = FastAPI(title="API YouTube Audio Splitter")

# Configuração: Tamanho máximo de cada pedaço em segundos (ex: 45 minutos = 2700s)
# Isso garante que o servidor aguente processar sem estourar memória/tempo.
CHUNK_SIZE_SECONDS = 2700 

class PartInfo(BaseModel):
    part_number: int
    start_time: int
    end_time: int
    download_url: str

class VideoAnalysis(BaseModel):
    title: str
    duration_total: int
    total_parts: int
    parts: list[PartInfo]

# --- Funções Auxiliares ---

def clean_filename(title: str) -> str:
    return "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip()

def cleanup_old_files():
    """Remove arquivos antigos para liberar espaço"""
    try:
        files = glob.glob("part_*.mp3")
        for f in files:
            # Se o arquivo tem mais de 20 minutos, deleta
            if os.path.getmtime(f) < time.time() - 1200: 
                os.remove(f)
    except:
        pass

# --- Endpoints ---

@app.get("/")
def home():
    return {"message": "API Splitter Online. Use /analyze para começar."}

@app.get("/analyze", response_model=VideoAnalysis)
def analyze_video(url: str, server_url: str = Query(..., description="A URL base da sua API (ex: https://api.com)")):
    """
    Passo 1: Analisa o vídeo e retorna o plano de corte (Quantas partes baixar).
    """
    try:
        ydl_opts = {
            'cookiefile': 'cookies.txt',
            'user_agent': 'Mozilla/5.0',
            'noplaylist': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # extract_info com download=False é super rápido, só pega metadados
            info = ydl.extract_info(url, download=False)
            duration = info.get('duration', 0)
            title = info.get('title', 'video_desconhecido')

        if not duration:
            raise HTTPException(status_code=400, detail="Não foi possível determinar a duração do vídeo.")

        # Lógica de Divisão
        parts = []
        num_parts = math.ceil(duration / CHUNK_SIZE_SECONDS)
        
        for i in range(num_parts):
            start = i * CHUNK_SIZE_SECONDS
            end = min((i + 1) * CHUNK_SIZE_SECONDS, duration)
            
            # Monta a URL que o usuário deve chamar para baixar esse pedaço
            dl_link = f"{server_url.rstrip('/')}/download-part?url={url}&start={start}&end={end}&part={i+1}"
            
            parts.append({
                "part_number": i + 1,
                "start_time": start,
                "end_time": end,
                "download_url": dl_link
            })

        return {
            "title": title,
            "duration_total": duration,
            "total_parts": num_parts,
            "parts": parts
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download-part")
def download_part(
    url: str, 
    start: int, 
    end: int, 
    part: int = 1
):
    """
    Passo 2: Baixa e converte apenas o intervalo de tempo solicitado.
    """
    cleanup_old_files() # Limpeza preventiva
    
    filename_base = f"part_{part}_{int(time.time())}"
    
    # Função auxiliar para filtrar o intervalo
    def download_range_func(info, ydl):
        return [{
            'start_time': start,
            'end_time': end
        }]

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            
            # --- O PULO DO GATO: DOWNLOAD POR INTERVALO ---
            'download_ranges': download_range_func,
            'force_keyframes_at_cuts': False, # False é mais rápido, True é mais preciso no corte
            
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'outtmpl': filename_base,
            'cookiefile': 'cookies.txt',
            # Timeouts e Retries para garantir estabilidade
            'socket_timeout': 30,
            'retries': 10,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            real_title = info.get('title', 'audio_part')

        final_filename = f"{filename_base}.mp3"
        
        if not os.path.exists(final_filename):
            raise HTTPException(status_code=500, detail="Erro na conversão do arquivo.")

        # Nome bonito para o download do usuário
        user_filename = f"{clean_filename(real_title)}_Parte{part}.mp3"

        return FileResponse(
            path=final_filename, 
            filename=user_filename, 
            media_type='audio/mpeg'
        )

    except Exception as e:
        print(f"Erro: {e}")
        raise HTTPException(status_code=500, detail=str(e))
