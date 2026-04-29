FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 (오디오 처리용)
RUN apt-get update && apt-get install -y \
    libportaudio2 \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "run_forever.py"]
