# Hafif bir Python imajı seçiyoruz
FROM python:3.11-slim

# Çalışma dizinini oluştur
WORKDIR /app

# Sistem bağımlılıklarını yükle (Gerekirse)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Gereksinimleri kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Tüm proje dosyalarını kopyala
COPY . .

# Flask'ın konteyner içinde dış dünyaya açılacağı port
EXPOSE 5000

# Uygulamayı başlat
CMD ["python", "app.py"]
