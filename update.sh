#!/bin/bash
echo "🚀 SentinelAi Güncelleniyor ve Başlatılıyor..."

# Sanal ortamı kontrol et ve aktif et (Windows Git Bash uyumlu)
if [ -d ".venv" ]; then
    echo "📦 Sanal ortam aktif ediliyor..."
    source .venv/Scripts/activate
elif [ -d "venv" ]; then
    echo "📦 Sanal ortam aktif ediliyor..."
    source venv/Scripts/activate
else
    echo "⚠️ Sanal ortam (venv) bulunamadı, sistem python'ı kullanılacak."
fi

# Gereklilikleri yükle
echo "📥 Bağımlılıklar kontrol ediliyor ve yükleniyor..."
pip install -r requirements.txt

# Uygulamayı başlat
echo "⚡ SentinelAi Sunucusu Başlatılıyor..."
python app.py
