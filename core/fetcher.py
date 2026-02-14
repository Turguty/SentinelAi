import feedparser
import sqlite3
import json
import os
import time
import requests
from core.ai_manager import AIManager

DB_PATH = 'data/sentinel.db'

# Keyword filtering for specific interests
KEYWORDS = ["Vakıfbank", "f5 waf", "crowdstrike", "paloalto", "twistlock", "guardicore", "vulnerability", "exploit", "cve"]

def send_telegram_message(message):
    """
    Sends a message to a Telegram chat using bot token and chat id from .env.
    """
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("[Uyarı] Telegram token veya chat id bulunamadı.")
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
        print(f"[Hata] Telegram gönderim hatası: {e}")

def init_db():
    """
    Uygulama için gerekli veritabanını ve 'news' tablosunu başlatır.
    """
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

def fetch_rss():
    """
    sources.json içindeki tüm RSS kaynaklarını tarar, yeni haberleri AI ile analiz eder 
    ve Telegram üzerinden bilgilendirme yapar.
    """
    init_db()
    ai_manager = AIManager()
    
    with open('sources.json', 'r') as f:
        sources = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for source in sources['sources']:
        if not source.get('active', True): continue
        print(f"[Taraniyor] {source['name']}")
        feed = feedparser.parse(source['url'])
        
        for entry in feed.entries:
            title = entry.title
            link = entry.link
            published = entry.get('published', 'Bilinmiyor')
            
            # Veritabanında var mı kontrol et
            cursor.execute("SELECT id FROM news WHERE link = ?", (link,))
            if cursor.fetchone():
                continue

            print(f"[Yeni Haber] {title}")
            
            # AI Analizi Al
            prompt = f"Analizine 'TEHDIT SEVIYESI: [KRITIK/ORTA/DUSUK]' ile başla.\nHaber: {title}\nLink: {link}"
            analysis = ai_manager.analyze(prompt)
            
            # Veritabanına kaydet
            try:
                cursor.execute(
                    "INSERT INTO news (title, link, published, source, ai_analysis) VALUES (?, ?, ?, ?, ?)",
                    (title, link, published, source['name'], analysis)
                )
                conn.commit()
                
                # Telegram Bildirimi: Eğer anahtar kelimelerden biri geçiyorsa veya genel siber güvenlik haberi ise
                is_urgent = any(kw.lower() in title.lower() for kw in KEYWORDS)
                if is_urgent:
                    telegram_msg = f"🚨 *KRİTİK HABER TESPİT EDİLDİ*\n\n*Başlık:* {title}\n*Kaynak:* {source['name']}\n\n*AI Analizi:*\n{analysis}\n\n[Habere Git]({link})"
                    send_telegram_message(telegram_msg)
                else:
                    telegram_msg = f"📰 *Yeni Siber Güvenlik Haberi*\n\n*Başlık:* {title}\n\n*AI Analizi:*\n{analysis}\n\n[Habere Git]({link})"
                    send_telegram_message(telegram_msg)

                # AI servislerini yormamak için kısa bir mola
                time.sleep(3)

            except Exception as e:
                print(f"[Hata] Kayit hatasi: {e}")

        
    conn.close()
    print("[Tamam] Tarama ve analiz tamamlandi.")

if __name__ == "__main__":
    fetch_rss()

