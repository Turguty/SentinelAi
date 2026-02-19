@echo off
:: Terminal kod sayfasini UTF-8 yap
chcp 65001 > nul

:: Python'u UTF-8 moduna zorla
set PYTHONUTF8=1

echo 🚀 SentinelAi Güncelleniyor ve Başlatılıyor...

:: Sanal ortamı kontrol et ve aktif et
if exist .venv\Scripts\activate (
    echo 📦 Sanal ortam aktif ediliyor...
    call .venv\Scripts\activate
) else if exist venv\Scripts\activate (
    echo 📦 Sanal ortam aktif ediliyor...
    call venv\Scripts\activate
) else (
    echo ⚠️ Sanal ortam bulunamadı, sistem python'ı kullanılacak.
)

:: Gereklilikleri yükle
echo 📥 Bağımlılıklar kontrol ediliyor...
pip install -q --disable-pip-version-check -r requirements.txt

:: Uygulamayı başlat
echo ⚡ SentinelAi başlatılıyor...
python app.py

pause
