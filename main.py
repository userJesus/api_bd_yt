from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import glob
import math
import time

app = FastAPI(title="API YouTube Audio Splitter (Precision Fix)")

# Configuração: Tamanho de cada pedaço (45 minutos)
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
    # Limpa nome do arquivo para evitar erro no sistema de arquivos
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
    return {"message": "API Splitter Precision Online. Use /analyze para começar."}

@app.get("/analyze", response_model=VideoAnalysis)
def analyze_video(url: str, server_url: str = Query(..., description="A URL base da sua API")):
    """
    Passo 1: Analisa o vídeo e retorna o plano de corte.
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
            raise HTTPException(status_code=400, detail="Não foi possível determinar a duração. Verifique se é uma Live ativa.")

        parts = []
        num_parts = math.ceil(duration / CHUNK_SIZE_SECONDS)
        
        for i in range(num_parts):
            start = i * CHUNK_SIZE_SECONDS
            end = min((i + 1) * CHUNK_SIZE_SECONDS, duration)
            
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
    Passo 2: Baixa com precisão de frames usando FFmpeg.
    """
    cleanup_old_files()
    
    filename_base = f"part_{part}_{int(time.time())}"
    
    def download_range_func(info, ydl):
        return [{'start_time': start, 'end_time': end}]

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'download_ranges': download_range_func,
            
            # --- CORREÇÃO DE PRECISÃO DE ÁUDIO ---
            # 1. Força re-encode nas pontas do corte para evitar silêncio/glitch
            'force_keyframes_at_cuts': True,
            
            # 2. Usa o FFmpeg como downloader (mais preciso para slices que o nativo)
            'external_downloader': 'ffmpeg',
            'external_downloader_args': {
                'ffmpeg_i': ['-ss', str(start), '-to', str(end)]
            },
            
            # --- CORREÇÃO SSL ---
            'nocheckcertificate': True,
            
            # Conversão final para MP3
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            
            'outtmpl': filename_base,
            'cookiefile': 'cookies.txt',
            
            # Resiliência
            'socket_timeout': 30,
            'retries': 10,
            'ignoreerrors': True,
        }

        # Executa o download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            real_title = info.get('title', 'audio_part')

        final_filename = f"{filename_base}.mp3"
        
        # Verificação extra de arquivo
        if not os.path.exists(final_filename):
            # As vezes o FFmpeg salva com extensão diferente antes de converter
            possiveis = glob.glob(f"{filename_base}.*")
            if possiveis:
                # Se achou algo (ex: .m4a), tenta retornar ele ou renomear
                final_filename = possiveis[0]
            else:
                raise HTTPException(status_code=500, detail="Erro: Arquivo de áudio não gerado.")

        user_filename = f"{clean_filename(real_title)}_Parte{part}.mp3"

        return FileResponse(
            path=final_filename, 
            filename=user_filename, 
            media_type='audio/mpeg'
        )

    except Exception as e:
        if os.path.exists(f"{filename_base}.mp3"):
            os.remove(f"{filename_base}.mp3")
        raise HTTPException(status_code=500, detail=f"Erro no download: {str(e)}")
