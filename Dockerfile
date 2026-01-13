# Usa uma imagem leve do Python
FROM python:3.10-slim

# Instala dependências do sistema (git e ffmpeg se decidir usar no futuro)
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Define a pasta de trabalho
WORKDIR /app

# Copia os arquivos de requisitos primeiro (para aproveitar o cache)
COPY requirements.txt .

# Instala as dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código
COPY . .

# Expõe a porta que o FastAPI/Uvicorn vai usar
EXPOSE 8000

# Comando para rodar a API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
