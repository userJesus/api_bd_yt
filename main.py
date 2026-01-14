from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import glob
import math
import time
import gc # Garbage Collector para limpar RAM

app = FastAPI(title="API YouTube Audio Splitter (Optimized)")

# Constantes
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

# --- Funções Auxiliares ---

def clean_filename(title: str) -> str:
    return "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip()

def cleanup_old_files():
    """Remove arquivos antigos e força limpeza de RAM"""
    try:
        files = glob.glob("part_*.mp3")
        for f in files:
            if os.path.getmtime(f) < time.time() - 1200: 
                os.remove(f)
        gc.collect() # Força limpeza de memória RAM
    except:
        pass

# --- Endpoints ---

@app.get("/")
def home():
    return {"message": "API Smart Splitter Optimized. Use /analyze"}

@app.get("/analyze", response_model=VideoAnalysis)
def analyze_video(url: str, server_url: str = Query(..., description="URL base da sua API")):
    """
    Passo 1: Analisa levemente (sem baixar nada pesado).
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
            raise HTTPException(status_code=400, detail="Não foi possível pegar a duração.")

        parts = []

        # Lógica de decisão (Inteiro vs Fatiado)
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
    Passo 2: Baixa OTIMIZADO (Menos CPU/RAM).
    """
    cleanup_old_files()
    filename_base = f"part_{part}_{int(time.time())}"
    
    def download_range_func(info, ydl):
        return [{'start_time': start, 'end_time': end}]

    try:
        ydl_opts = {
            # OTIMIZAÇÃO 1: Baixa o melhor áudio disponível (geralmente m4a/opus)
            # Evita baixar vídeo para extrair áudio.
            'format': 'bestaudio/best',
            
            # Recorte preciso
            'download_ranges': download_range_func,
            'force_keyframes_at_cuts': True, # Mantém a precisão, mas deixa o yt-dlp gerenciar
            
            # OTIMIZAÇÃO 2: Configurações de Rede e Buffer (Economia de RAM)
            'concurrent_fragment_downloads': 1, # Não baixar múltiplos pedaços ao mesmo tempo
            'buffersize': 1024, # Buffer pequeno
            'http_chunk_size': 1048576, # Baixa em blocos de 1MB (suave para a rede)
            
            # OTIMIZAÇÃO 3: Post-Processamento Leve
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128', # 128k é o equilíbrio perfeito. Acima disso gasta CPU à toa.
            }],
            
            # Flags para o FFmpeg (Prioriza velocidade na conversão)
            'postprocessor_args': [
                '-threads', '1',  # Usa apenas 1 núcleo do processador por conversão (não trava o servidor)
                '-preset', 'ultrafast' # Tenta codificar o mais rápido possível
            ],
            
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

        final_filename = f"{filename_base}.mp3"
        
        if not os.path.exists(final_filename):
            possiveis = glob.glob(f"{filename_base}.*")
            final_filename = possiveis[0] if possiveis else None
            
        if not final_filename:
             raise HTTPException(status_code=500, detail="Erro: Arquivo não gerado.")

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
