from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import glob
import math
import time
import gc

app = FastAPI(title="API Splitter (Robust + Low CPU)")

# Configurações
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

# --- Utils ---
def clean_filename(title: str) -> str:
    return "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip()

def cleanup_old_files():
    try:
        # Remove qualquer lixo de download antigo
        for ext in ["mp3", "m4a", "webm", "part"]:
            for f in glob.glob(f"*.{ext}"):
                if os.path.getmtime(f) < time.time() - 1200: 
                    os.remove(f)
        gc.collect()
    except:
        pass

# --- Endpoints ---
@app.get("/")
def home():
    return {"message": "API Robust Online"}

@app.get("/analyze", response_model=VideoAnalysis)
def analyze_video(url: str, server_url: str = Query(..., description="URL base")):
    try:
        ydl_opts = {
            'cookiefile': 'cookies.txt',
            'user_agent': 'Mozilla/5.0',
            'noplaylist': True,
            'nocheckcertificate': True,
            'socket_timeout': 30,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get('duration', 0)
            title = info.get('title', 'video_desconhecido')

        if not duration:
            # Fallback para lives ou erros de leitura
            # Assume 1 parte se não conseguir ler duração
            duration = 1
        
        parts = []
        
        # Se for muito curto ou erro de leitura, faz download único
        if duration <= LIMIT_SINGLE_PART:
            parts.append({
                "part_number": 1,
                "start_time": 0,
                "end_time": duration if duration > 1 else None, # None baixa tudo
                "download_url": f"{server_url.rstrip('/')}/download-part?url={url}&start=0&end={duration}&part=1"
            })
            num_parts = 1
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
        raise HTTPException(status_code=500, detail=f"Erro Analyze: {str(e)}")

@app.get("/download-part")
def download_part(url: str, start: int, end: int, part: int = 1):
    cleanup_old_files()
    filename_base = f"part_{part}_{int(time.time())}"
    
    # Define range apenas se end > 1 (evita erro em vídeos sem duração)
    def download_range_func(info, ydl):
        if end and end > 1:
            return [{'start_time': start, 'end_time': end}]
        return None

    try:
        ydl_opts = {
            # CORREÇÃO 1: Aceita TUDO (bestaudio/best). 
            # Se não tiver M4A, baixa WebM e converte. Resolve o erro "Format not available".
            'format': 'bestaudio/best',
            
            'download_ranges': download_range_func,
            'force_keyframes_at_cuts': True,
            
            # CORREÇÃO 2: Limites de CPU e Buffer
            'concurrent_fragment_downloads': 1,
            'buffersize': 1024,
            
            # CORREÇÃO 3: Conversão MP3 Leve (1 thread)
            # Garante que funciona em qualquer player, mas não trava o servidor
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'postprocessor_args': [
                '-threads', '1',       # Usa SÓ 1 núcleo
                '-preset', 'ultrafast' # Velocidade máxima
            ],

            'nocheckcertificate': True, # Resolve erro SSL
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
        
        # Verificação final
        if not os.path.exists(final_filename):
            # Procura por qualquer arquivo gerado se a conversão falhou
            possiveis = glob.glob(f"{filename_base}.*")
            if possiveis:
                final_filename = possiveis[0]
            else:
                raise HTTPException(status_code=500, detail="Erro: Download falhou (arquivo não criado). Tente atualizar o yt-dlp.")

        # Nome amigável
        ext = final_filename.split('.')[-1]
        user_filename = f"{clean_filename(real_title)}_Parte{part}.{ext}"
        mime = 'audio/mpeg' if ext == 'mp3' else 'audio/mp4'

        return FileResponse(path=final_filename, filename=user_filename, media_type=mime)

    except Exception as e:
        if os.path.exists(f"{filename_base}.mp3"): os.remove(f"{filename_base}.mp3")
        raise HTTPException(status_code=500, detail=f"Erro Download: {str(e)}")
