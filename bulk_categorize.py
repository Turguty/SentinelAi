"""
Bulk Categorization Script
---------------------------
Veritabanındaki tüm haberleri AI ile kategorilendiren tek seferlik script.
Kullanım: python bulk_categorize.py
"""

import sqlite3
import time
from core.ai_manager import AIManager
from core.logger import setup_logger

logger = setup_logger("BulkCategorize")
DB_PATH = 'data/sentinel.db'

# Geçerli kategori listesi
VALID_CATEGORIES = ["Malware", "Phishing", "Ransomware", "Vulnerability", "Breach", "DDoS", "APT", "Data Leak", "General"]

def extract_category(analysis_text, title=""):
    """AI analizinden ve başlıktan kategoriyi çıkarır - geliştirilmiş versiyon."""
    # Hem analiz hem başlığı birleştir
    combined_text = f"{title} {analysis_text or ''}".lower()
    
    if not combined_text.strip():
        return "General"
    
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
    
    # Her kategori için anahtar kelimeleri kontrol et
    for category, keywords in category_keywords.items():
        for keyword in keywords:
            if keyword in combined_text:
                return category
    
    return "General"

def is_security_related(title, analysis):
    """Haberin güvenlikle alakalı olup olmadığını kontrol eder."""
    combined = f"{title} {analysis or ''}".lower()
    
    # Güvenlik anahtar kelimeleri
    security_keywords = [
        "cyber", "security", "exploit", "cve", "vulnerability", "malware", 
        "hack", "breach", "ransomware", "zero-day", "leak", "threat", "attack",
        "phishing", "ddos", "botnet", "apt", "trojan", "virus", "worm", "backdoor",
        "spyware", "güvenlik", "zafiyet", "saldırı", "tehdit", "fidye"
    ]
    
    # Alakasız anahtar kelimeler (ürün incelemeleri, teknoloji haberleri vb.)
    irrelevant_keywords = [
        "best deal", "sale", "discount", "review", "unboxing", "hands-on",
        "galaxy s", "iphone", "airpods", "roku", "tv", "soundbar", "air purifier",
        "presidents' day", "black friday", "cyber monday", "gift guide"
    ]
    
    # Önce alakasız mı kontrol et
    for keyword in irrelevant_keywords:
        if keyword in combined:
            return False
    
    # Güvenlik kelimesi var mı kontrol et
    for keyword in security_keywords:
        if keyword in combined:
            return True
    
    return False

def categorize_all_news():
    """Tüm haberleri kategorilendiren ve alakasız olanları silen ana fonksiyon."""
    logger.info("🚀 Toplu kategorilendirme ve temizlik başlatılıyor...")
    
    ai_manager = AIManager()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    
    # Tüm haberleri çek
    cursor.execute("""
        SELECT id, title, ai_analysis, category 
        FROM news 
        ORDER BY id DESC
    """)
    
    news_items = cursor.fetchall()
    total = len(news_items)
    
    if total == 0:
        logger.info("✅ İşlenecek haber bulunamadı!")
        conn.close()
        return
    
    logger.info(f"📊 Toplam {total} haber kontrol edilecek.")
    
    processed = 0
    updated = 0
    deleted = 0
    errors = 0
    
    for news_id, title, ai_analysis, current_category in news_items:
        processed += 1
        
        try:
            # Güvenlikle alakalı mı kontrol et
            if not is_security_related(title, ai_analysis):
                logger.info(f"[{processed}/{total}] 🗑️ Alakasız haber siliniyor: {title[:60]}...")
                cursor.execute("DELETE FROM news WHERE id = ?", (news_id,))
                conn.commit()
                deleted += 1
                continue
            
            # Kategori kontrolü - sadece General veya boş olanları güncelle
            if current_category in [None, '', 'General']:
                category = extract_category(ai_analysis, title)
                
                # Eğer hala General ise ve AI analizi yoksa, yeni analiz yap
                if category == "General" and not ai_analysis:
                    logger.info(f"[{processed}/{total}] 🧠 Yeni AI analizi yapılıyor: {title[:60]}...")
                    
                    prompt = (
                        f"Bu bir siber güvenlik haberi mi? Kısaca analiz et ve kategori belirt.\n"
                        f"KATEGORI: [Malware/Phishing/Ransomware/Vulnerability/Breach/DDoS/APT/Data Leak/General]\n"
                        f"Haber: {title}"
                    )
                    
                    analysis = ai_manager.analyze(prompt)
                    category = extract_category(analysis, title)
                    
                    cursor.execute(
                        "UPDATE news SET ai_analysis = ?, category = ? WHERE id = ?",
                        (analysis, category, news_id)
                    )
                    
                    time.sleep(2)  # API rate limit koruması
                else:
                    # Sadece kategoriyi güncelle
                    cursor.execute(
                        "UPDATE news SET category = ? WHERE id = ?",
                        (category, news_id)
                    )
                
                conn.commit()
                updated += 1
                logger.info(f"✅ [{processed}/{total}] Güncellendi: {category}")
            else:
                logger.info(f"[{processed}/{total}] ⏭️ Zaten kategorili: {current_category}")
            
        except Exception as e:
            errors += 1
            logger.error(f"❌ [{processed}/{total}] Hata (ID: {news_id}): {e}")
            continue
    
    conn.close()
    
    logger.info("=" * 60)
    logger.info(f"🎉 İşlem tamamlandı!")
    logger.info(f"📊 İşlenen: {processed} | Güncellenen: {updated} | Silinen: {deleted} | Hata: {errors}")
    logger.info("=" * 60)

if __name__ == "__main__":
    categorize_all_news()
