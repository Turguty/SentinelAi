import feedparser
import sqlite3
import json
import os
import time
import requests
from core.ai_manager import AIManager
from core.logger import setup_logger

# Loglama kurulumu
logger = setup_logger("Fetcher")

DB_PATH = 'data/sentinel.db'

# Önemli anahtar kelimeler (Telegram bildirimlerini tetikler)
KEYWORDS = ["Vakıfbank", "f5 waf", "crowdstrike", "paloalto", "twistlock", "guardicore", "vulnerability", "exploit", "cve"]

def send_telegram_message(message):
    """Belirlenen mesajı Telegram'a gönderir."""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"❌ Telegram Hatası: {e}")

def init_db():
    """Veritabanı yapısını kontrol eder ve tabloyu oluşturur."""
    if not os.path.exists('data'):
        os.makedirs('data')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            link TEXT UNIQUE,
            published TEXT,
            source TEXT,
            ai_analysis TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def process_missing_analysis():
    """Analizi henüz yapılmamış haberleri tespit eder ve tamamlar."""
    init_db()
    ai_manager = AIManager()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, title, link FROM news WHERE ai_analysis IS NULL OR ai_analysis LIKE 'HATA:%' LIMIT 10")
    missing_news = cursor.fetchall()
    
    if not missing_news:
        return

    logger.info(f"🧠 {len(missing_news)} eksik haber analiz ediliyor...")
    
    for row in missing_news:
        news_id, title, link = row
        prompt = f"Şu haberi teknik olarak analiz et:\n{title}\nLink: {link}"
        analysis = ai_manager.analyze(prompt)
        
        if analysis and not analysis.startswith("HATA:"):
            cursor.execute("UPDATE news SET ai_analysis = ? WHERE id = ?", (analysis, news_id))
            conn.commit()
            time.sleep(3) 
            
    conn.close()

def fetch_rss():
    """Tüm RSS kaynaklarını tarar ve yeni haberleri kaydeder."""
    init_db()
    ai_manager = AIManager()
    
    try:
        with open('sources.json', 'r') as f:
            sources = json.load(f)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        for source in sources['sources']:
            if not source.get('active', True): continue
            logger.info(f"📡 Tarama başlatıldı: {source['name']}")
            feed = feedparser.parse(source['url'])
            
            for entry in feed.entries:
                title = entry.title
                link = entry.link
                
                cursor.execute("SELECT id FROM news WHERE link = ?", (link,))
                if cursor.fetchone(): continue

                logger.info(f"💡 Yeni haber bulundu: {title[:70]}...")
                
                # Anlık analiz
                prompt = f"Kısa bir tehdit analizi yap:\nHaberi: {title}"
                analysis = ai_manager.analyze(prompt)
                
                try:
                    cursor.execute(
                        "INSERT INTO news (title, link, published, source, ai_analysis) VALUES (?, ?, ?, ?, ?)",
                        (title, link, entry.get('published', 'Bilinmiyor'), source['name'], analysis)
                    )
                    conn.commit()
                    
                    # Telegram Bildirimi
                    is_urgent = any(kw.lower() in title.lower() for kw in KEYWORDS)
                    header = "🚨 *KRİTİK HABER*" if is_urgent else "📰 *YENİ HABER*"
                    telegram_msg = f"{header}\n\n*Başlık:* {title}\n*Kaynak:* {source['name']}\n\n*AI:* {analysis[:300]}...\n\n[Habere Git]({link})"
                    send_telegram_message(telegram_msg)

                    time.sleep(3) 

                except Exception as e:
                    logger.error(f"❌ Kayıt Hatası: {e}")
        
        conn.close()
        logger.info("✨ Tarama ve analiz süreci tamamlandı.")
    except Exception as e:
        logger.error(f"RSS Tarama Hatası: {e}")

if __name__ == "__main__":
    fetch_rss()
