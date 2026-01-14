# Usa uma imagem Python leve baseada em Linux (Debian)
FROM python:3.9-slim

# 1. Instala o FFmpeg no sistema operacional
# Isso é OBRIGATÓRIO para o yt-dlp conseguir converter áudio para MP3
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Define o diretório de trabalho dentro do container
WORKDIR /app

# 2. Copia o requirements.txt e instala as dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copia todo o resto do código (main.py, cookies.txt, etc.)
COPY . .

# Expõe a porta padrão do FastAPI
EXPOSE 8000

# Comando para iniciar o servidor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
