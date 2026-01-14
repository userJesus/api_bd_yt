from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import glob
import time
import gc

app = FastAPI(title="API Smart Splitter (No Orphan Parts)")

# --- Configuração de Tempos ---
LIMIT_SINGLE_PART = 3599  # Até 59m 59s: Link único
CHUNK_SIZE_LONG = 1800    # Alvo de 30 minutos por parte
MIN_REMAINDER = 90        # PROTEÇÃO: Se sobrar menos de 90s (1min e meio), junta com a parte anterior.

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
            if os.path.getmtime(f) < time.time() - 1200: 
                os.remove(f)
        gc.collect()
    except:
        pass

# --- Endpoints ---

@app.get("/")
def home():
    return {"message": "API Smart Splitter Online (No Orphan Segments)."}

@app.get("/analyze", response_model=VideoAnalysis)
def analyze_video(url: str, server_url: str = Query(..., description="A URL base da sua API")):
    """
    Passo 1: Analisa e cria plano de corte INTELIGENTE.
    Evita criar partes finais com poucos segundos.
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
            duration = 1 

        parts = []

        # --- LÓGICA DE DIVISÃO INTELIGENTE ---
        
        # CASO 1: Vídeo curto (<= 59:59) -> Baixa inteiro
        if duration <= LIMIT_SINGLE_PART:
            dl_link = f"{server_url.rstrip('/')}/download-part?url={url}&start=0&end={duration}&part=1"
            parts.append({
                "part_number": 1,
                "start_time": 0,
                "end_time": duration,
                "download_url": dl_link
            })
            
        else:
            # CASO 2: Vídeo Longo -> Loop dinâmico para evitar sobras pequenas
            current_start = 0
            part_count = 1
            
            while current_start < duration:
                # O alvo ideal é 30 minutos a frente
                target_end = current_start + CHUNK_SIZE_LONG
                
                # VERIFICAÇÃO DE SOBRA:
                # Se o que sobrar depois desse corte for menor que o Mínimo (ex: 90s),
                # esticamos este corte até o final do vídeo.
                remaining_after_cut = duration - target_end
                
                if remaining_after_cut > 0 and remaining_after_cut < MIN_REMAINDER:
                    target_end = duration # Come a sobra
                
                # Garante que não passamos do final real
                final_end = min(target_end, duration)
                
                dl_link = f"{server_url.rstrip('/')}/download-part?url={url}&start={current_start}&end={final_end}&part={part_count}"
                
                parts.append({
                    "part_number": part_count,
                    "start_time": current_start,
                    "end_time": final_end,
                    "download_url": dl_link
                })
                
                # Prepara para o próximo loop
                current_start = final_end
                part_count += 1
                
                # Se já chegamos ao fim, para
                if current_start >= duration:
                    break

        return {
            "title": title,
            "duration_total": duration,
            "total_parts": len(parts),
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
    Passo 2: Download otimizado.
    """
    cleanup_old_files()
    
    filename_base = f"part_{part}_{int(time.time())}"
    
    def download_range_func(info, ydl):
        if end > start:
            return [{'start_time': start, 'end_time': end}]
        return None

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'download_ranges': download_range_func,
            'force_keyframes_at_cuts': False,
            
            # Correção SSL e CPU
            'nocheckcertificate': True,
            
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            
            # Post-Processamento Leve (1 Thread)
            'postprocessor_args': [
                '-threads', '1',
                '-preset', 'ultrafast'
            ],

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
            if possiveis:
                final_filename = possiveis[0]
            else:
                raise HTTPException(status_code=500, detail="Erro: Arquivo MP3 não gerado.")

        user_filename = f"{clean_filename(real_title)}_Parte{part}.mp3"

        return FileResponse(
            path=final_filename, 
            filename=user_filename, 
            media_type='audio/mpeg'
        )

    except Exception as e:
        if os.path.exists(f"{filename_base}.mp3"):
            try: os.remove(f"{filename_base}.mp3")
            except: pass
        raise HTTPException(status_code=500, detail=f"Erro no download: {str(e)}")
