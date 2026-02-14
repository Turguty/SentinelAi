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
from pydantic import BaseModel, ValidationError, Field
from typing import Optional

# Yerel modüller
from core.ai_manager import AIManager
from core.fetcher import fetch_rss, process_missing_analysis
from core.logger import setup_logger

# Loglama kurulumu
logger = setup_logger("App")

# .env dosyasındaki değişkenleri yükle
load_dotenv()

def auto_install_requirements():
    """requirements.txt dosyasındaki bağımlılıkları kontrol eder ve eksik olanları otomatik yükler."""
    try:
        logger.info("📦 Bağımlılıklar kontrol ediliyor...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    except Exception as e:
        logger.error(f"❌ Bağımlılık yükleme hatası: {e}")

# Uygulama başlamadan önce bağımlılıkları kontrol et
auto_install_requirements()

app = Flask(__name__)
DB_PATH = 'data/sentinel.db'
ai_manager = AIManager()

# --- Veri Doğrulama Modelleri (Pydantic) ---
class AnalyzeRequest(BaseModel):
    title: str = Field(..., min_length=5)
    link: str

class CveRequest(BaseModel):
    id: str = Field(..., pattern=r'^CVE-\d{4}-\d+$')

class IpRequest(BaseModel):
    ip: str = Field(..., min_length=1)

class DnsRequest(BaseModel):
    domain: str = Field(..., min_length=3)


# Arka Plan Görevleri (Scheduler) Yapılandırması
scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_rss, trigger="interval", minutes=15)
scheduler.add_job(func=process_missing_analysis, trigger="interval", minutes=5)
scheduler.start()

atexit.register(lambda: scheduler.shutdown())

def get_db_connection():
    """SQLite veritabanına bağlantı oluşturur."""
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
    """Veritabanındaki haberleri sayfalama ve arama kriterlerine göre getirir."""
    try:
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
    except Exception as e:
        logger.error(f"Haber çekme hatası: {e}")
        return jsonify({"error": "Sistem hatası"}), 500

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
def analyze_news_route():
    """Belirli bir haberi manuel olarak analiz eder (Doğrulamalı)."""
    try:
        # Pydantic ile veri doğrula
        req_data = AnalyzeRequest(**request.json)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ai_analysis FROM news WHERE link = ?", (req_data.link,))
        existing = cursor.fetchone()
        
        if existing and existing[0] and not existing[0].startswith("HATA:"):
            conn.close()
            return jsonify({"analysis": existing[0]})

        prompt = f"Analizine 'TEHDIT SEVIYESI: [KRITIK/ORTA/DUSUK]' ile başla.\nHaber: {req_data.title}\nLink: {req_data.link}"
        analysis_result = ai_manager.analyze(prompt)

        if analysis_result and not analysis_result.startswith("HATA:"):
            cursor.execute("UPDATE news SET ai_analysis = ? WHERE link = ?", (analysis_result, req_data.link))
            conn.commit()
        
        conn.close()
        return jsonify({"analysis": analysis_result})
    except ValidationError as e:
        return jsonify({"error": "Geçersiz veri formatı", "details": e.errors()}), 400
    except Exception as e:
        logger.error(f"Manuel analiz hatası: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/cve', methods=['GET'])
def analyze_cve_route():
    """CVE ID üzerinden istihbarat toplar ve AI ile teknik yorum ekler (Doğrulamalı)."""
    try:
        cve_id = request.args.get('id', '').strip().upper()
        # Doğrulama
        CveRequest(id=cve_id)

        res = requests.get(f"https://cve.circl.lu/api/cve/{cve_id}", timeout=15)
        if res.status_code == 200:
            data = res.json()
            if not data: return jsonify({"error": "CVE bulunamadı"}), 404
            
            summary = data.get('summary', 'Açıklama bulunamadı.')
            cvss = data.get('cvss', 'Bilinmiyor')
            
            context = f"Özet: {summary}" if summary != "Açıklama bulunamadı." else f"{cve_id} özelinde zafiyet yorumu yap."
            prompt = f"Siber güvenlik uzmanı olarak analiz et:\nCVE: {cve_id}\nCVSS: {cvss}\n{context}"
            ai_comment = ai_manager.analyze(prompt)
            
            return jsonify({
                "id": cve_id,
                "summary": summary,
                "cvss": cvss,
                "ai_comment": ai_comment,
                "references": data.get('references', [])[:5]
            })
        return jsonify({"error": "Dış servis hatası"}), 502
    except ValidationError:
        return jsonify({"error": "Geçersiz CVE formatı (Örn: CVE-2024-1234)"}), 400
    except Exception as e:
        logger.error(f"CVE sorgu hatası: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/ip', methods=['GET'])
def analyze_ip_route():
    """IP adresi üzerinden konum ve ISP istihbaratı toplar."""
    try:
        ip_addr = request.args.get('ip', '').strip()
        IpRequest(ip=ip_addr)

        res = requests.get(f"http://ip-api.com/json/{ip_addr}?fields=status,message,country,city,isp,org,as,query", timeout=10)
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
        return jsonify({"error": "Servis ulaşılamadı"}), 502
    except ValidationError:
        return jsonify({"error": "Geçersiz IP adresi"}), 400
    except Exception as e:
        logger.error(f"IP sorgu hatası: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/dns', methods=['GET'])
def analyze_dns_route():
    """Verilen domain için tüm kritik DNS kayıtlarını sorgular."""
    try:
        domain = request.args.get('domain', '').strip()
        DnsRequest(domain=domain)

        import dns.resolver
        results = {"domain": domain, "records": {}}
        record_types = ['A', 'NS', 'CNAME', 'MX', 'TXT']
        
        for rtype in record_types:
            try:
                answers = dns.resolver.resolve(domain, rtype)
                results["records"][rtype] = [str(r) for r in answers]
            except:
                results["records"][rtype] = []

        if not any(results["records"].values()):
            return jsonify({"error": "Kayıt bulunamadı"}), 404

        return jsonify(results)
    except ValidationError:
        return jsonify({"error": "Geçersiz domain adı"}), 400
    except Exception as e:
        logger.error(f"DNS sorgu hatası: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    logger.info("🚀 SentinelAi Sunucusu Başlatılıyor...")
    app.run(host='0.0.0.0', port=5000, debug=True)
