from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import glob
import math
import time
import gc

app = FastAPI(title="API Audio Splitter (Low CPU - M4A)")

# Constantes
LIMIT_SINGLE_PART = 3599
CHUNK_SIZE_LONG = 1800

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
    try:
        files = glob.glob("part_*.m4a") # Alterado para remover .m4a
        for f in files:
            if os.path.getmtime(f) < time.time() - 1200: 
                os.remove(f)
        gc.collect()
    except:
        pass

# --- Endpoints ---

@app.get("/")
def home():
    return {"message": "API Low CPU Online. Format: M4A (Native)"}

@app.get("/analyze", response_model=VideoAnalysis)
def analyze_video(url: str, server_url: str = Query(..., description="URL base da sua API")):
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
            raise HTTPException(status_code=400, detail="Não foi possível pegar a duração.")

        parts = []

        if duration <= LIMIT_SINGLE_PART:
            num_parts = 1
            dl_link = f"{server_url.rstrip('/')}/download-part?url={url}&start=0&end={duration}&part=1"
            parts.append({"part_number": 1, "start_time": 0, "end_time": duration, "download_url": dl_link})
        else:
            chunk_size = CHUNK_SIZE_LONG
            num_parts = math.ceil(duration / chunk_size)
            for i in range(num_parts):
                start = i * chunk_size
                end = min((i + 1) * chunk_size, duration)
                dl_link = f"{server_url.rstrip('/')}/download-part?url={url}&start={start}&end={end}&part={i+1}"
                parts.append({"part_number": i+1, "start_time": start, "end_time": end, "download_url": dl_link})

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
    Passo 2: Download Otimizado (M4A Nativo + Limite de CPU).
    """
    cleanup_old_files()
    filename_base = f"part_{part}_{int(time.time())}"
    
    def download_range_func(info, ydl):
        return [{'start_time': start, 'end_time': end}]

    try:
        ydl_opts = {
            # 1. BAIXA DIRETO EM M4A (Formato nativo leve)
            # Isso evita a conversão pesada para MP3
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio',
            
            'download_ranges': download_range_func,
            'force_keyframes_at_cuts': True, # Mantém a precisão do áudio
            
            # 2. LIMITA O DOWNLOAD
            'concurrent_fragment_downloads': 1,
            'buffersize': 1024,
            
            # 3. LIMITA O USO DE CPU NO FFMPEG
            'postprocessor_args': [
                '-threads', '1',       # Usa APENAS 1 núcleo (evita o pico de 400%)
                '-preset', 'ultrafast', # Prioriza velocidade
                '-vn'                  # Garante que remove vídeo se vier junto
            ],
            
            # NÃO USAMOS 'FFmpegExtractAudio' com codec mp3 aqui.
            # Deixamos nativo ou convertemos levemente para m4a/aac se necessário
            
            'nocheckcertificate': True,
            'outtmpl': filename_base,
            'cookiefile': 'cookies.txt',
            'socket_timeout': 30,
            'retries': 10,
            'ignoreerrors': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            real_title = info.get('title', 'audio_part')

        # O arquivo provavelmente será .m4a ou .webm (opus)
        # Vamos procurar qualquer extensão gerada
        possiveis = glob.glob(f"{filename_base}.*")
        final_filename = possiveis[0] if possiveis else None
            
        if not final_filename:
             raise HTTPException(status_code=500, detail="Erro: Arquivo não gerado.")

        # Extensão correta para o usuário
        ext = final_filename.split('.')[-1]
        user_filename = f"{clean_filename(real_title)}_Parte{part}.{ext}"
        
        # Define o media_type correto
        mime_type = 'audio/mp4' if ext == 'm4a' else 'audio/mpeg'

        return FileResponse(
            path=final_filename, 
            filename=user_filename, 
            media_type=mime_type
        )

    except Exception as e:
        # Tenta limpar lixo
        for f in glob.glob(f"{filename_base}.*"):
            os.remove(f)
        raise HTTPException(status_code=500, detail=f"Erro no download: {str(e)}")
