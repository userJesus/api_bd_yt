from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import glob
import math
import time
import gc

app = FastAPI(title="API Splitter (Ultra Fast - Native)")

# Configurações
LIMIT_SINGLE_PART = 3599  # Até 59:59 em 1 link
CHUNK_SIZE_LONG = 1800    # 30 minutos por parte

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
        # Remove arquivos antigos de qualquer extensão de áudio
        for ext in ["m4a", "webm", "mp3", "mp4", "part"]:
            for f in glob.glob(f"*.{ext}"):
                if os.path.getmtime(f) < time.time() - 1200: 
                    os.remove(f)
        gc.collect()
    except:
        pass

# --- Endpoints ---
@app.get("/")
def home():
    return {"message": "API Ultra Fast Online"}

@app.get("/analyze", response_model=VideoAnalysis)
def analyze_video(url: str, server_url: str = Query(..., description="URL base")):
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

        # Fallback se duração falhar
        if not duration: duration = 1
        
        parts = []
        
        # Lógica de Divisão
        if duration <= LIMIT_SINGLE_PART:
            # Vídeo Curto (1 parte)
            parts.append({
                "part_number": 1,
                "start_time": 0,
                "end_time": duration,
                "download_url": f"{server_url.rstrip('/')}/download-part?url={url}&start=0&end={duration}&part=1"
            })
            num_parts = 1
        else:
            # Vídeo Longo (Fatias de 30min)
            num_parts = math.ceil(duration / CHUNK_SIZE_LONG)
            for i in range(num_parts):
                start = i * CHUNK_SIZE_LONG
                end = min((i + 1) * CHUNK_SIZE_LONG, duration)
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
    
    def download_range_func(info, ydl):
        # Só aplica range se for um corte real (evita erro em vídeos curtos ou lives)
        if end > 0 and end < 100000: 
            return [{'start_time': start, 'end_time': end}]
        return None

    try:
        ydl_opts = {
            # 1. FORMATO: Prioriza M4A (leve e compatível). Aceita WebM se for o único.
            # NÃO força conversão. Baixa o que vier.
            'format': 'bestaudio[ext=m4a]/bestaudio',
            
            # 2. CORTE LEVE: Desativa keyframes forçados.
            # Isso faz o yt-dlp baixar os bytes exatos sem reprocessar CPU.
            'download_ranges': download_range_func,
            'force_keyframes_at_cuts': False, 
            
            # 3. SEM POST-PROCESSORS PESADOS
            # Removemos o FFmpegExtractAudio convertendo para MP3.
            # O arquivo será entregue como .m4a ou .webm (Original).
            
            # Otimizações de Rede
            'concurrent_fragment_downloads': 1,
            'buffersize': 1024,
            
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

        # Detecta qual arquivo foi baixado (m4a, webm, etc)
        possiveis = glob.glob(f"{filename_base}.*")
        final_filename = possiveis[0] if possiveis else None
            
        if not final_filename:
             raise HTTPException(status_code=500, detail="Erro: Arquivo não gerado. Tente atualizar o yt-dlp.")

        # Define extensão e tipo MIME corretos
        ext = final_filename.split('.')[-1]
        user_filename = f"{clean_filename(real_title)}_Parte{part}.{ext}"
        
        # Tipos MIME suportados pela maioria dos players
        if ext == 'm4a': mime = 'audio/mp4'
        elif ext == 'webm': mime = 'audio/webm'
        else: mime = 'application/octet-stream'

        return FileResponse(path=final_filename, filename=user_filename, media_type=mime)

    except Exception as e:
        # Limpeza de erro
        for f in glob.glob(f"{filename_base}.*"):
            try: os.remove(f)
            except: pass
        raise HTTPException(status_code=500, detail=f"Erro Download: {str(e)}")
