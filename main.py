from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import glob
import math
import time

app = FastAPI(title="API YouTube Audio Splitter (Smart Logic)")

# Constantes de Tempo
LIMIT_SINGLE_PART = 3599  # 59 minutos e 59 segundos
CHUNK_SIZE_LONG = 1800    # 30 minutos (para vídeos longos)

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
    # Remove caracteres perigosos do nome do arquivo
    return "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip()

def cleanup_old_files():
    """Remove arquivos antigos (mais de 20min) para liberar espaço"""
    try:
        files = glob.glob("part_*.mp3")
        for f in files:
            if os.path.getmtime(f) < time.time() - 1200: 
                os.remove(f)
    except:
        pass

# --- Endpoints ---

@app.get("/")
def home():
    return {"message": "API Smart Splitter Online. Use /analyze"}

@app.get("/analyze", response_model=VideoAnalysis)
def analyze_video(url: str, server_url: str = Query(..., description="URL base da sua API")):
    """
    Passo 1: Analisa e decide se divide ou não.
    Regra: <= 59:59 vai inteiro. > 59:59 divide em blocos de 30min.
    """
    try:
        ydl_opts = {
            'cookiefile': 'cookies.txt',
            'user_agent': 'Mozilla/5.0',
            'noplaylist': True,
            'nocheckcertificate': True, 
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get('duration', 0)
            title = info.get('title', 'video_desconhecido')

        if not duration:
            raise HTTPException(status_code=400, detail="Não foi possível determinar a duração.")

        parts = []

        # --- LÓGICA DE DECISÃO ---
        if duration <= LIMIT_SINGLE_PART:
            # CASO 1: Vídeo Curto (Até 59:59) -> 1 Parte Única
            num_parts = 1
            dl_link = f"{server_url.rstrip('/')}/download-part?url={url}&start=0&end={duration}&part=1"
            
            parts.append({
                "part_number": 1,
                "start_time": 0,
                "end_time": duration,
                "download_url": dl_link
            })
            
        else:
            # CASO 2: Vídeo Longo (> 59:59) -> Fatiar em 30 min
            chunk_size = CHUNK_SIZE_LONG
            num_parts = math.ceil(duration / chunk_size)
            
            for i in range(num_parts):
                start = i * chunk_size
                end = min((i + 1) * chunk_size, duration)
                
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
        raise HTTPException(status_code=500, detail=f"Erro na análise: {str(e)}")


@app.get("/download-part")
def download_part(
    url: str, 
    start: int, 
    end: int, 
    part: int = 1
):
    """
    Passo 2: Baixa o trecho solicitado com precisão máxima.
    """
    cleanup_old_files()
    
    filename_base = f"part_{part}_{int(time.time())}"
    
    def download_range_func(info, ydl):
        return [{'start_time': start, 'end_time': end}]

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'download_ranges': download_range_func,
            
            # Precisão de Áudio (Evita silêncio no início)
            'force_keyframes_at_cuts': True,
            
            # Engine de Download (FFmpeg é melhor para cortes)
            'external_downloader': 'ffmpeg',
            'external_downloader_args': {
                'ffmpeg_i': ['-ss', str(start), '-to', str(end)]
            },
            
            # Segurança SSL
            'nocheckcertificate': True,
            
            # Conversão para MP3 leve
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            
            'outtmpl': filename_base,
            'cookiefile': 'cookies.txt',
            'socket_timeout': 30,
            'retries': 10,
            'ignoreerrors': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            real_title = info.get('title', 'audio_part')

        final_filename = f"{filename_base}.mp3"
        
        # Fallback para caso a extensão mude
        if not os.path.exists(final_filename):
            possiveis = glob.glob(f"{filename_base}.*")
            if possiveis:
                final_filename = possiveis[0]
            else:
                raise HTTPException(status_code=500, detail="Erro: Arquivo não gerado.")

        user_filename = f"{clean_filename(real_title)}_Parte{part}.mp3"

        return FileResponse(
            path=final_filename, 
            filename=user_filename, 
            media_type='audio/mpeg'
        )

    except Exception as e:
        # Limpeza de erro
        if os.path.exists(f"{filename_base}.mp3"):
            os.remove(f"{filename_base}.mp3")
        raise HTTPException(status_code=500, detail=f"Erro no download: {str(e)}")
