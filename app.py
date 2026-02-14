import os
import sqlite3
import time
import requests
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template, request, jsonify
from core.ai_manager import AIManager
from core.fetcher import fetch_rss, process_missing_analysis
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

app = Flask(__name__)
DB_PATH = 'data/sentinel.db'
ai_manager = AIManager()

# Arka Plan Görevleri (Scheduler)
scheduler = BackgroundScheduler()
# 15 dakikada bir yeni haberleri çek
scheduler.add_job(func=fetch_rss, trigger="interval", minutes=15)
# 5 dakikada bir eksik analizleri tamamla
scheduler.add_job(func=process_missing_analysis, trigger="interval", minutes=5)
scheduler.start()

# Uygulama kapandığında scheduler'ı da kapat
atexit.register(lambda: scheduler.shutdown())

@app.route('/')

def index():
    return render_template('index.html')

# SQLite bağlantı yardımcısı (Kilitlenmeleri önlemek için)
def get_db_connection():
    """Veritabanına bağlanır ve sonuçları sözlük formatında dönecek şekilde ayarlar."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/api/ai_status', methods=['GET'])
def get_ai_status():
    """Hangi AI servislerinin aktif olduğunu döner."""
    return jsonify(ai_manager.get_status())

@app.route('/api/news', methods=['GET'])

def get_news():
    """
    Kayıtlı haberleri getirir. Sayfalama ve arama filtrelerini destekler.
    """
    page = int(request.args.get('page', 1))
    search_query = request.args.get('search', '')
    per_page = 10
    offset = (page - 1) * per_page

    conn = get_db_connection()
    cursor = conn.cursor()

    # Sayfalama için toplam sayı
    if search_query:
        cursor.execute("SELECT COUNT(*) FROM news WHERE title LIKE ?", ('%' + search_query + '%',))
    else:
        cursor.execute("SELECT COUNT(*) FROM news")
    total_count = cursor.fetchone()[0]

    # Haberleri çek
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
    """Haber kaynaklarının dağılım istatistiklerini döner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT source, COUNT(*) as count FROM news GROUP BY source ORDER BY count DESC")
    sources = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"sources": sources})

@app.route('/api/intensity', methods=['GET'])
def get_intensity():
    """Son 7 günün haber yoğunluğunu döner."""
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
    Belirli bir haberi AI ile analiz eder. Sonuç veritabanında varsa oradan getirir,
    yoksa AI servislerini kullanarak yeni analiz oluşturur.
    """
    data = request.json
    title, link = data.get('title'), data.get('link')
    if not title or not link: return jsonify({"error": "Eksik"}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT ai_analysis FROM news WHERE link = ?", (link,))
    existing = cursor.fetchone()
    
    # Eğer önceden analiz varsa VE bu analiz bir hata mesajı DEĞİLSE mevcut olanı dön
    if existing and existing[0] and not existing[0].startswith("HATA:"):
        conn.close()
        return jsonify({"analysis": existing[0]})

    prompt = f"Analizine 'TEHDIT SEVIYESI: [KRITIK/ORTA/DUSUK]' ile başla.\nHaber: {title}\nLink: {link}"
    analysis_result = ai_manager.analyze(prompt)

    # Eğer yeni analiz başarılıysa veritabanını güncelle
    if analysis_result and not analysis_result.startswith("HATA:"):
        cursor.execute("UPDATE news SET ai_analysis = ? WHERE link = ?", (analysis_result, link))
        conn.commit()
    
    conn.close()
    return jsonify({"analysis": analysis_result})


@app.route('/api/cve', methods=['GET'])
def analyze_cve():
    """CVE bilgilerini çeker ve AI ile yorumlar."""
    cve_id = request.args.get('id', '').strip().upper()
    if not cve_id: return jsonify({"error": "CVE ID gerekli"}), 400
    
    try:
        # CIRCL CVE API kullanımı
        res = requests.get(f"https://cve.circl.lu/api/cve/{cve_id}", timeout=15)
        if res.status_code == 200:
            data = res.json()
            if not data: return jsonify({"error": "CVE bulunamadı"}), 404
            
            summary = data.get('summary', 'Açıklama bulunamadı.')
            cvss = data.get('cvss', 'Bilinmiyor')
            
            # Eğer özet yoksa AI'ya sadece ID üzerinden genel bilgi sormasını söyle
            context = f"Özet: {summary}" if summary != "Açıklama bulunamadı." else f"Bu CVE ID ({cve_id}) hakkında bildiğin genel bilgileri ve genel siber güvenlik prensiplerini kullanarak analiz yap."

            prompt = (
                f"Şu CVE hakkında detaylı teknik analiz yap ve siber güvenlik uzmanı olarak yorumla:\n\n"
                f"CVE ID: {cve_id}\n"
                f"CVSS Skoru: {cvss}\n"
                f"{context}\n\n"
                f"Lütfen şunları açıkla:\n"
                f"1. Zafiyetin genel ciddiyeti (CVSS'ye göre)\n"
                f"2. Bu tip zafiyetler için olası saldırı senaryosu\n"
                f"3. Savunma stratejileri ve acil aksiyonlar\n"
                f"Cevap dili: Türkçe"
            )
            ai_comment = ai_manager.analyze(prompt)

            
            return jsonify({
                "id": cve_id,
                "summary": summary,
                "cvss": cvss,
                "ai_comment": ai_comment,
                "references": data.get('references', [])[:5]
            })
        return jsonify({"error": "CVE servisine ulaşılamadı"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/ip', methods=['GET'])
def analyze_ip():
    """IP adresi hakkında istihbarat toplar."""
    ip = request.args.get('ip', '').strip()
    if not ip: return jsonify({"error": "IP adresi gerekli"}), 400
    
    try:
        # IP-API kullanımı (Ücretsiz ve basit)
        res = requests.get(f"http://ip-api.com/json/{ip}?fields=status,message,country,city,isp,org,as,query", timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data['status'] == 'fail': return jsonify({"error": "IP bilgisi alınamadı"}), 404
            
            return jsonify({
                "ip": data['query'],
                "location": f"{data.get('city')}, {data.get('country')}",
                "isp": data.get('isp'),
                "org": data.get('org'),
                "as": data.get('as')
            })
        return jsonify({"error": "IP servisine ulaşılamadı"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/dns', methods=['GET'])
def analyze_dns():
    """Domain için DNS (A) ve Name Server (NS) kayıtlarını sorgular."""
    domain = request.args.get('domain', '').strip()
    if not domain: return jsonify({"error": "Domain gerekli"}), 400
    
    import dns.resolver
    results = {"domain": domain, "records": {}}
    
    try:
        # A Kayıtları
        try:
            a_records = dns.resolver.resolve(domain, 'A')
            results["records"]["A"] = [str(r) for r in a_records]
        except: results["records"]["A"] = []
            
        # NS Kayıtları
        try:
            ns_records = dns.resolver.resolve(domain, 'NS')
            results["records"]["NS"] = [str(r) for r in ns_records]
        except: results["records"]["NS"] = []

        if not results["records"]["A"] and not results["records"]["NS"]:
            return jsonify({"error": "Kayıt bulunamadı veya geçersiz domain"}), 404

        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':


    app.run(host='0.0.0.0', port=5000, debug=True)
