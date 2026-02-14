import os
import sqlite3
import time
import requests
import subprocess
import sys
import atexit
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from core.ai_manager import AIManager
from core.fetcher import fetch_rss, process_missing_analysis

# .env dosyasındaki değişkenleri yükle
load_dotenv()

def auto_install_requirements():
    """
    requirements.txt dosyasındaki bağımlılıkları kontrol eder ve eksik olanları otomatik yükler.
    Bu sayede yeni bir kütüphane eklendiğinde manuel işlem gerekmez.
    """
    try:
        print("📦 Bağımlılıklar kontrol ediliyor...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Tüm bağımlılıklar güncel.")
    except Exception as e:
        print(f"❌ Bağımlılık yükleme hatası: {e}")

# Uygulama başlamadan önce bağımlılıkları kontrol et
auto_install_requirements()

app = Flask(__name__)
DB_PATH = 'data/sentinel.db'
ai_manager = AIManager()

# Arka Plan Görevleri (Scheduler) Yapılandırması
scheduler = BackgroundScheduler()
# 15 dakikada bir yeni haberleri çek ve Telegram'a at
scheduler.add_job(func=fetch_rss, trigger="interval", minutes=15)
# 5 dakikada bir veritabanındaki analizsiz haberleri tamamla
scheduler.add_job(func=process_missing_analysis, trigger="interval", minutes=5)
scheduler.start()

# Uygulama kapandığında scheduler'ı düzgün şekilde durdur
atexit.register(lambda: scheduler.shutdown())

def get_db_connection():
    """
    SQLite veritabanına bağlantı oluşturur. 
    Sonuçları Row objesi olarak döner (sözlük benzeri erişim için).
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    """Ana sayfa dashboard arayüzünü yükler."""
    return render_template('index.html')

@app.route('/api/ai_status', methods=['GET'])
def get_ai_status():
    """AI servislerinin o anki aktiflik/soğuma durumlarını döner."""
    return jsonify(ai_manager.get_status())

@app.route('/api/news', methods=['GET'])
def get_news():
    """
    Veritabanındaki haberleri sayfalama ve arama kriterlerine göre getirir.
    """
    page = int(request.args.get('page', 1))
    search_query = request.args.get('search', '')
    per_page = 10
    offset = (page - 1) * per_page

    conn = get_db_connection()
    cursor = conn.cursor()

    if search_query:
        cursor.execute("SELECT COUNT(*) FROM news WHERE title LIKE ?", ('%' + search_query + '%',))
    else:
        cursor.execute("SELECT COUNT(*) FROM news")
    total_count = cursor.fetchone()[0]

    if search_query:
        cursor.execute(
            "SELECT * FROM news WHERE title LIKE ? ORDER BY published DESC LIMIT ? OFFSET ?",
            ('%' + search_query + '%', per_page, offset)
        )
    else:
        cursor.execute(
            "SELECT * FROM news ORDER BY published DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        )
    
    rows = cursor.fetchall()
    conn.close()
    
    return jsonify({
        "news": [dict(row) for row in rows],
        "total": total_count,
        "current_page": page,
        "per_page": per_page
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Haberlerin kaynaklara göre dağılım istatistiklerini hesaplar."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT source, COUNT(*) as count FROM news GROUP BY source ORDER BY count DESC")
    sources = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"sources": sources})

@app.route('/api/intensity', methods=['GET'])
def get_intensity():
    """Son 7 gün içindeki haber giriş yoğunluğunu döner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT date(COALESCE(created_at, CURRENT_TIMESTAMP)) as date, COUNT(*) as count 
        FROM news 
        WHERE created_at >= date('now', '-7 days') OR created_at IS NULL
        GROUP BY date
        ORDER BY date ASC
    """)
    intensity = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"intensity": intensity})

@app.route('/api/analyze', methods=['POST'])
def analyze_news():
    """
    Belirli bir haberi manuel olarak analiz eder. 
    Eğer hata varsa yeniden deneme (retry) mekanizması içerir.
    """
    data = request.json
    title, link = data.get('title'), data.get('link')
    if not title or not link: return jsonify({"error": "Başlık veya link eksik"}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT ai_analysis FROM news WHERE link = ?", (link,))
    existing = cursor.fetchone()
    
    # Hata döndüren eski analizler varsa yeniden yapılmasına izin ver
    if existing and existing[0] and not existing[0].startswith("HATA:"):
        conn.close()
        return jsonify({"analysis": existing[0]})

    prompt = f"Analizine 'TEHDIT SEVIYESI: [KRITIK/ORTA/DUSUK]' ile başla.\nHaber: {title}\nLink: {link}"
    analysis_result = ai_manager.analyze(prompt)

    if analysis_result and not analysis_result.startswith("HATA:"):
        cursor.execute("UPDATE news SET ai_analysis = ? WHERE link = ?", (analysis_result, link))
        conn.commit()
    
    conn.close()
    return jsonify({"analysis": analysis_result})

@app.route('/api/cve', methods=['GET'])
def analyze_cve():
    """CVE ID üzerinden istihbarat toplar ve AI ile teknik yorum ekler."""
    cve_id = request.args.get('id', '').strip().upper()
    if not cve_id: return jsonify({"error": "CVE ID gerekli"}), 400
    
    try:
        # CIRCL CVE API üzerinden teknik verileri çek
        res = requests.get(f"https://cve.circl.lu/api/cve/{cve_id}", timeout=15)
        if res.status_code == 200:
            data = res.json()
            if not data: return jsonify({"error": "CVE bulunamadı"}), 404
            
            summary = data.get('summary', 'Açıklama bulunamadı.')
            cvss = data.get('cvss', 'Bilinmiyor')
            
            # AI Analiz Kapsamı
            context = f"Özet: {summary}" if summary != "Açıklama bulunamadı." else f"{cve_id} özelinde bilinen zafiyet tiplerine göre yorum yap."
            prompt = (
                f"Siber güvenlik analisti olarak analiz et:\n"
                f"CVE ID: {cve_id}\nCVSS: {cvss}\n{context}\n\n"
                f"Analiz şunları içermeli: Ciddiyet, Saldırı Senaryosu, Savunma Önerileri (Türkçe)."
            )
            ai_comment = ai_manager.analyze(prompt)
            
            return jsonify({
                "id": cve_id,
                "summary": summary,
                "cvss": cvss,
                "ai_comment": ai_comment,
                "references": data.get('references', [])[:5]
            })
        return jsonify({"error": "Dış servis hatası"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/ip', methods=['GET'])
def analyze_ip():
    """IP adresi üzerinden konum ve ISP istihbaratı toplar."""
    ip = request.args.get('ip', '').strip()
    if not ip: return jsonify({"error": "IP adresi gerekli"}), 400
    
    try:
        res = requests.get(f"http://ip-api.com/json/{ip}?fields=status,message,country,city,isp,org,as,query", timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data['status'] == 'fail': return jsonify({"error": "IP bulunamadı"}), 404
            return jsonify({
                "ip": data['query'],
                "location": f"{data.get('city')}, {data.get('country')}",
                "isp": data.get('isp'),
                "org": data.get('org'),
                "as": data.get('as')
            })
        return jsonify({"error": "Ulaşılamadı"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/dns', methods=['GET'])
def analyze_dns():
    """Verilen domain için tüm kritik DNS kayıtlarını sorgular."""
    domain = request.args.get('domain', '').strip()
    if not domain: return jsonify({"error": "Domain gerekli"}), 400
    
    import dns.resolver
    results = {"domain": domain, "records": {}}
    record_types = ['A', 'NS', 'CNAME', 'MX', 'TXT']
    
    try:
        for rtype in record_types:
            try:
                answers = dns.resolver.resolve(domain, rtype)
                results["records"][rtype] = [str(r) for r in answers]
            except:
                results["records"][rtype] = []

        if not any(results["records"].values()):
            return jsonify({"error": "Kayıt bulunamadı"}), 404

        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Flask sunucusunu başlat
    app.run(host='0.0.0.0', port=5000, debug=True)
