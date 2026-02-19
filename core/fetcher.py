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

    conn.commit()
    conn.close()


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
        return

    logger.info(f"🧠 {len(missing_news)} eksik haber analiz ediliyor...")
    
    # Kuyruk yoğunluğu kontrolü: 20'den fazla haber varsa Load Balance aktif et
    use_lb = len(missing_news) > 20
    if use_lb:
        logger.info("⚖️ Kuyruk yoğunluğu ( >20 ) nedeniyle Load Balance aktif edildi.")

    for row in missing_news:
        news_id, title, link = row
        prompt = (
            f"Analizine 'TEHDIT SEVIYESI: [KRITIK/ORTA/DUSUK]' ve 'KATEGORI: [Malware/Phishing/Ransomware/Vulnerability/Breach/General]' ile başla.\n"
            f"Haber: {title}\nLink: {link}"
        )
        analysis = ai_manager.analyze(prompt, use_load_balance=use_lb)
        
        if analysis and not analysis.startswith("HATA:"):
            # Kategoriyi ayıkla ve doğrula
            category = "General"
            valid_categories = ["Malware", "Phishing", "Ransomware", "Vulnerability", "Breach", "General"]
            
            if "KATEGORI:" in analysis:
                try: 
                    raw_cat = analysis.split("KATEGORI:")[1].split("]")[0].replace("[", "").strip()
                    found = False
                    for valid in valid_categories:
                        if valid.lower() in raw_cat.lower():
                            category = valid
                            found = True
                            break
                    if not found and len(raw_cat) > 20: 
                        category = "General"
                    elif not found:
                        category = raw_cat[:20]
                except: pass

            cursor.execute("UPDATE news SET ai_analysis = ?, category = ? WHERE id = ?", (analysis, category, news_id))
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

        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
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

                # Güvenlik odaklı filtreleme: Başlıkta anahtar kelime yoksa veya açıkça alakasızsa atla
                security_keywords = ["cyber", "security", "exploit", "cve", "vulnerability", "malware", "hack", "breach", "ransomware", "zero-day", "leak", "threat", "attack"]
                content_text = (title + " " + entry.get('summary', '')).lower()
                is_security_related = any(kw in content_text for kw in security_keywords)
                
                if not is_security_related:
                    # AI analizi yerine varsayılan olarak düşük seviyeli ve genel kategorili kaydet (isteğe bağlı)
                    # Veya tamamen atla:
                    continue

                logger.info(f"💡 Yeni güvenlik haberi bulundu: {title[:70]}...")
                
                # Anlık analiz
                prompt = (
                    f"Analizine 'TEHDIT SEVIYESI: [KRITIK/ORTA/DUSUK]' ve 'KATEGORI: [Malware/Phishing/Ransomware/Vulnerability/Breach/General]' ile başla.\n"
                    f"Haberi: {title}"
                )
                analysis = ai_manager.analyze(prompt)
                
                # Kategoriyi akıllı şekilde çıkar (anahtar kelime bazlı)
                def extract_category_from_analysis(text):
                    if not text:
                        return "General"
                    
                    text_lower = text.lower()
                    
                    # Öncelik sırasına göre kategorileri kontrol et
                    category_keywords = {
                        "Ransomware": ["ransomware", "fidye", "ransom"],
                        "Malware": ["malware", "trojan", "virus", "worm", "rat", "stealer", "backdoor", "spyware", "stalkerware"],
                        "Phishing": ["phishing", "phish", "sosyal mühendislik", "social engineering"],
                        "DDoS": ["ddos", "denial of service", "botnet"],
                        "APT": ["apt", "advanced persistent"],
                        "Vulnerability": ["vulnerability", "zafiyet", "cve-", "zero-day", "zero day", "exploit"],
                        "Breach": ["breach", "data leak", "veri sızıntısı", "ihlal", "leak"],
                        "Data Leak": ["data leak", "veri sızıntısı"]
                    }
                    
                    for category, keywords in category_keywords.items():
                        for keyword in keywords:
                            if keyword in text_lower:
                                return category
                    
                    return "General"
                
                category = extract_category_from_analysis(analysis)

                try:
                    cursor.execute(
                        "INSERT INTO news (title, link, published, source, ai_analysis, category) VALUES (?, ?, ?, ?, ?, ?)",
                        (title, link, entry.get('published', 'Bilinmiyor'), source['name'], analysis, category)
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
    init_db()
    fetch_rss()
