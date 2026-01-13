from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import yt_dlp
import os
import glob

app = FastAPI()

@app.get("/")
def home():
    return {"message": "API de Download de Áudio (MP3) está online!"}

@app.get("/baixar")
def baixar_audio(url: str):
    try:
        # 1. Limpeza: Remove arquivos de downloads anteriores para não encher o disco
        files = glob.glob("downloaded_audio*")
        for f in files:
            try:
                os.remove(f)
            except:
                pass

        # 2. Configuração Blindada
        ydl_opts = {
            # O SEGREDO: 'bestaudio/best' 
            # Diz para o script: "Baixe qualquer áudio que tiver. Se não tiver áudio separado, baixe o vídeo."
            # Isso elimina o erro "Requested format is not available".
            'format': 'bestaudio/best',

            # Otimizações de Rede (Para vídeos longos não caírem)
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            
            # Post-Processamento: Converte QUALQUER coisa que baixou para MP3 leve
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128', # 128kbps é qualidade padrão do YouTube (ótimo tamanho/qualidade)
            }],

            # Caminhos e Arquivos
            'outtmpl': 'downloaded_audio', # O script vai adicionar .mp3 automaticamente depois
            'noplaylist': True,
            
            # Autenticação (Necessária para servidores)
            'cookiefile': 'cookies.txt',
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            
            # Evita travar em metadados obscuros
            'ignoreerrors': True,
            'no_warnings': True,
        }

        print(f"Iniciando download de: {url}")

        # 3. Execução do Download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Tenta pegar o título, se falhar usa um genérico
            titulo_original = info.get('title', 'audio_youtube')
            
            # Remove caracteres inválidos do título para evitar erro no navegador
            titulo_safe = "".join([c for c in titulo_original if c.isalnum() or c in (' ', '-', '_')]).strip() + ".mp3"

        # O arquivo final gerado pelo FFmpeg será sempre .mp3
        filename = "downloaded_audio.mp3"

        if not os.path.exists(filename):
            raise HTTPException(status_code=500, detail="Erro: O arquivo de áudio não foi gerado pelo FFmpeg.")

        # 4. Retorno do Arquivo
        return FileResponse(
            path=filename, 
            filename=titulo_safe, 
            media_type='audio/mpeg'
        )

    except Exception as e:
        # Loga o erro no console do Docker e retorna para o usuário
        print(f"ERRO CRÍTICO: {str(e)}")
        return HTTPException(status_code=500, detail=f"ERROR: {str(e)}")
