import feedparser
import sqlite3
import json
import os
import time
import requests
from core.ai_manager import AIManager
from core.logger import setup_logger
from core.prompts import ANALYSIS_SYSTEM_PROMPT, generate_news_prompt

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
    """Veritabanı yapısını kontrol eder ve tabloyu oluşturur/günceller."""
    if not os.path.exists('data'):
        os.makedirs('data')
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    
    # Ana tabloyu oluştur (yoksa)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            link TEXT UNIQUE,
            published TEXT,
            source TEXT,
            ai_analysis TEXT,
            category TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migration: 'category' sütunu var mı kontrol et, yoksa ekle
    cursor.execute("PRAGMA table_info(news)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'category' not in columns:
        logger.info("🛠️ Veritabanı şeması güncelleniyor: 'category' sütunu ekleniyor...")
        cursor.execute("ALTER TABLE news ADD COLUMN category TEXT")
        
    # İndeksler (Performans için)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_published ON news(published)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_category ON news(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_source ON news(source)")

    conn.commit()
    conn.close()

def parse_ai_json_to_text(json_data):
    """JSON analiz sonucunu veritabanı formatına (string) çevirir."""
    if not json_data:
        return "Analiz yapılamadı."
    
    threat = json_data.get('threat_level', 'UNKNOWN')
    cat = json_data.get('category', 'General')
    summary = json_data.get('summary', '')
    details = json_data.get('technical_details', '')
    
    # Frontend formatına uygun string oluştur
    return f"❌ TEHDIT SEVIYESI: [{threat}]\n📂 KATEGORI: [{cat}]\n\n📝 Özet: {summary}\n\n⚙️ Teknik Detay: {details}"

def process_missing_analysis():
    """Analizi henüz yapılmamış haberleri tespit eder ve tamamlar."""
    init_db()
    ai_manager = AIManager()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, title, link FROM news WHERE ai_analysis IS NULL OR ai_analysis LIKE 'HATA:%' LIMIT 10")
    missing_news = cursor.fetchall()
    
    if not missing_news:
        conn.close()
        return

    logger.info(f"🧠 {len(missing_news)} eksik haber analiz ediliyor...")
    
    # Kuyruk yoğunluğu kontrolü: 20'den fazla haber varsa Load Balance aktif et
    use_lb = len(missing_news) > 20
    if use_lb:
        logger.info("⚖️ Kuyruk yoğunluğu ( >20 ) nedeniyle Load Balance aktif edildi.")

    for row in missing_news:
        news_id, title, link = row
        prompt = generate_news_prompt(title, link)
        
        # JSON Analizi
        json_result = ai_manager.analyze_json(prompt, system_prompt=ANALYSIS_SYSTEM_PROMPT)
        
        if json_result:
            analysis_text = parse_ai_json_to_text(json_result)
            category = json_result.get('category', 'General')
            
            cursor.execute("UPDATE news SET ai_analysis = ?, category = ? WHERE id = ?", (analysis_text, category, news_id))
            conn.commit()
            logger.info(f"✅ Haber güncellendi: {title[:30]}...")
            time.sleep(2) 
        else:
            # Hata durumunda
            logger.warning(f"⚠️ Analiz başarısız (ID: {news_id})")
            time.sleep(1)
            
    conn.close()

def fetch_rss():
    """Tüm RSS kaynaklarını tarar ve yeni haberleri kaydeder."""
    init_db()
    ai_manager = AIManager()
    
    try:
        with open('sources.json', 'r') as f:
            sources = json.load(f)

        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()

        for source in sources['sources']:
            if not source.get('active', True): continue
            logger.info(f"📡 Tarama başlatıldı: {source['name']}")
            try:
                feed = feedparser.parse(source['url'])
                
                for entry in feed.entries:
                    title = entry.title
                    link = entry.link
                    
                    cursor.execute("SELECT id FROM news WHERE link = ?", (link,))
                    if cursor.fetchone(): continue

                    # Güvenlik odaklı filtreleme
                    security_keywords = ["cyber", "security", "exploit", "cve", "vulnerability", "malware", "hack", "breach", "ransomware", "zero-day", "leak", "threat", "attack"]
                    content_text = (title + " " + entry.get('summary', '')).lower()
                    is_security_related = any(kw in content_text for kw in security_keywords)
                    
                    if not is_security_related:
                        continue

                    logger.info(f"💡 Yeni güvenlik haberi bulundu: {title[:70]}...")
                    
                    # Anlık analiz (JSON)
                    prompt = generate_news_prompt(title, link, content=entry.get('summary', ''))
                    json_result = ai_manager.analyze_json(prompt, system_prompt=ANALYSIS_SYSTEM_PROMPT)
                    
                    analysis_text = "Analiz Bekleniyor..."
                    category = "General"
                    
                    if json_result:
                        analysis_text = parse_ai_json_to_text(json_result)
                        category = json_result.get('category', 'General')
                    else:
                        # Fallback: Eğer AI anlık yanıt vermezse, sonradan process_missing_analysis tamamlar
                        analysis_text = None 

                    try:
                        cursor.execute(
                            "INSERT INTO news (title, link, published, source, ai_analysis, category) VALUES (?, ?, ?, ?, ?, ?)",
                            (title, link, entry.get('published', 'Bilinmiyor'), source['name'], analysis_text, category)
                        )
                        conn.commit()
                        
                        # Telegram Bildirimi
                        is_urgent = any(kw.lower() in title.lower() for kw in KEYWORDS)
                        header = "🚨 *KRİTİK HABER*" if is_urgent else "📰 *YENİ HABER*"
                        telegram_analysis = json_result.get('summary', 'Detaylar için siteye göz atın.') if json_result else "Analiz ediliyor..."
                        
                        telegram_msg = f"{header}\n\n*Başlık:* {title}\n*Kaynak:* {source['name']}\n\n*AI:* {telegram_analysis}\n\n[Habere Git]({link})"
                        send_telegram_message(telegram_msg)

                        time.sleep(2) 

                    except Exception as e:
                        logger.error(f"❌ Kayıt Hatası: {e}")
            except Exception as feed_err:
                logger.error(f"⚠️ RSS Okuma Hatası ({source['name']}): {feed_err}")
                continue
        
        conn.close()
        logger.info("✨ Tarama ve analiz süreci tamamlandı.")
    except Exception as e:
        logger.error(f"Genel RSS Döngü Hatası: {e}")

if __name__ == "__main__":
    init_db()
    fetch_rss()
