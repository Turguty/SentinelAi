import os
import sqlite3
import time
import requests
import subprocess
import sys
import atexit
import psutil
from flask import Flask, render_template, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from pydantic import BaseModel, ValidationError, Field
from typing import Optional

# Yerel modüller
from core.ai_manager import AIManager
from core.fetcher import fetch_rss, process_missing_analysis, init_db
from core.logger import setup_logger
from core.cache import get_cache, set_cache

logger = setup_logger("App")

# .env dosyasındaki değişkenleri yükle
load_dotenv()

def auto_install_requirements():
    """requirements.txt dosyasındaki bağımlılıkları kontrol eder ve eksik olanları otomatik yükler."""
    try:
        logger.info("📦 Bağımlılıklar kontrol ediliyor...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", "requirements.txt"])
    except Exception as e:
        logger.error(f"❌ Bağımlılık yükleme hatası: {e}")

# Uygulama başlamadan önce bağımlılıkları kontrol et
auto_install_requirements()

app = Flask(__name__)

# Hız Sınırlayıcı (Rate Limiter)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://",
)

DB_PATH = 'data/sentinel.db'
ai_manager = AIManager()
start_time = time.time()


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


@app.route('/api/system/health', methods=['GET'])
def get_system_health():
    """Sunucu CPU ve RAM kullanım bilgilerini döner."""
    # cpu_percent(interval=0.1) ilk çağrıda 0 dönmemesi için kısa bir ölçüm yapar
    return jsonify({
        "cpu": psutil.cpu_percent(interval=0.1),
        "ram": psutil.virtual_memory().percent,
        "uptime": int(time.time() - start_time)
    })

# Arka Plan Görevleri (Scheduler) Yapılandırması

scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_rss, trigger="interval", minutes=15)
scheduler.add_job(func=process_missing_analysis, trigger="interval", minutes=5)
scheduler.start()

atexit.register(lambda: scheduler.shutdown())

def get_db_connection():
    """SQLite veritabanına bağlantı oluşturur ve WAL modunu aktif eder."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    """Ana sayfa dashboard arayüzünü yükler."""
    return render_template('index.html')

@app.route('/api/ai_status', methods=['GET'])
def get_ai_status():
    """AI servislerinin durumunu ve bekleyen analiz sayısını döner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM news WHERE ai_analysis IS NULL OR ai_analysis LIKE 'HATA:%'")
    pending = cursor.fetchone()[0]
    conn.close()
    
    status = ai_manager.get_status()
    status['pending_analysis'] = pending
    return jsonify(status)

@app.route('/api/news', methods=['GET'])
def get_news():
    """Veritabanındaki haberleri sayfalama, arama ve kategori kriterlerine göre getirir."""
    try:
        page = int(request.args.get('page', 1))
        search_query = request.args.get('search', '')
        category_filter = request.args.get('category', '')
        per_page = 10
        offset = (page - 1) * per_page

        conn = get_db_connection()
        cursor = conn.cursor()

        # Dinamik SQL sorgusu oluştur
        base_query = "SELECT * FROM news"
        count_query = "SELECT COUNT(*) FROM news"
        conditions = []
        params = []

        if search_query:
            conditions.append("title LIKE ?")
            params.append('%' + search_query + '%')
        
        if category_filter:
            conditions.append("category = ?")
            params.append(category_filter)

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        
        # Toplam sayıyı al
        cursor.execute(count_query + where_clause, params)
        total_count = cursor.fetchone()[0]

        # Haberleri al
        cursor.execute(
            base_query + where_clause + " ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [per_page, offset]
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

@app.route('/api/stats/categories', methods=['GET'])
def get_category_stats():
    """Haberlerin tehdit kategorilerine göre dağılımını döner (Filtrelenmiş)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Sadece kısa ve anlamlı kategorileri getir (AI hatalı parse etmişse temizle)
    cursor.execute("""
        SELECT category, COUNT(*) as count 
        FROM news 
        WHERE category IS NOT NULL 
        AND length(category) < 25
        GROUP BY category 
        ORDER BY count DESC
    """)
    stats = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"categories": stats})

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

        prompt = (
            f"Analizine 'TEHDIT SEVIYESI: [KRITIK/ORTA/DUSUK]' ve 'KATEGORI: [Malware/Phishing/Ransomware/Vulnerability/Breach/General]' ile başla.\n"
            f"Haber: {req_data.title}\nLink: {req_data.link}"
        )
        analysis_result = ai_manager.analyze(prompt)

        if analysis_result and not analysis_result.startswith("HATA:"):
            # Kategoriyi ayıkla ve doğrula
            category = "General"
            valid_categories = ["Malware", "Phishing", "Ransomware", "Vulnerability", "Breach", "General"]
            
            if "KATEGORI:" in analysis_result:
                try: 
                    raw_cat = analysis_result.split("KATEGORI:")[1].split("]")[0].replace("[", "").strip()
                    # Whitelist kontrolü: Eğer çıkartılan kelime valid değilse "General" yap
                    found = False
                    for valid in valid_categories:
                        if valid.lower() in raw_cat.lower():
                            category = valid
                            found = True
                            break
                    if not found and len(raw_cat) > 20: # Eğer çok uzunsa muhtemelen hatalı parse
                        category = "General"
                    elif not found:
                        category = raw_cat[:20] # Limit length
                except: pass
            
            cursor.execute("UPDATE news SET ai_analysis = ?, category = ? WHERE link = ?", 
                           (analysis_result, category, req_data.link))
            conn.commit()
        
        conn.close()
        return jsonify({"analysis": analysis_result})
    except ValidationError as e:
        return jsonify({"error": "Geçersiz veri formatı", "details": e.errors()}), 400
    except Exception as e:
        logger.error(f"Manuel analiz hatası: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/cve', methods=['GET'])
@limiter.limit("10 per minute")
def analyze_cve_route():
    """CVE ID üzerinden istihbarat toplar ve AI ile teknik yorum ekler (Önbellekli)."""
    try:
        cve_id = request.args.get('id', '').strip().upper()
        CveRequest(id=cve_id)

        # Önbellek Kontrolü
        cached_data = get_cache(f"cve_{cve_id}")
        if cached_data: return jsonify(cached_data)

        res = requests.get(f"https://cve.circl.lu/api/cve/{cve_id}", timeout=15)
        if res.status_code == 200:
            data = res.json()
            if not data: return jsonify({"error": "CVE bulunamadı"}), 404
            
            summary = data.get('summary', 'Açıklama bulunamadı.')
            cvss = data.get('cvss', 'Bilinmiyor')
            
            context = f"Özet: {summary}" if summary != "Açıklama bulunamadı." else f"{cve_id} özelinde zafiyet yorumu yap."
            prompt = f"Siber güvenlik uzmanı olarak analiz et:\nCVE: {cve_id}\nCVSS: {cvss}\n{context}"
            ai_comment = ai_manager.analyze(prompt)
            
            result = {
                "id": cve_id,
                "summary": summary,
                "cvss": cvss,
                "ai_comment": ai_comment,
                "references": data.get('references', [])[:5]
            }
            set_cache(f"cve_{cve_id}", result)
            return jsonify(result)
        return jsonify({"error": "Dış servis hatası"}), 502
    except ValidationError:
        return jsonify({"error": "Geçersiz CVE formatı (Örn: CVE-2024-1234)"}), 400
    except Exception as e:
        logger.error(f"CVE sorgu hatası: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/ip', methods=['GET'])
@limiter.limit("20 per minute")
def analyze_ip_route():
    """IP adresi üzerinden konum ve ISP istihbaratı toplar (Önbellekli)."""
    try:
        ip_addr = request.args.get('ip', '').strip()
        IpRequest(ip=ip_addr)

        # Önbellek Kontrolü
        cached_data = get_cache(f"ip_{ip_addr}")
        if cached_data: return jsonify(cached_data)

        res = requests.get(f"http://ip-api.com/json/{ip_addr}?fields=status,message,country,city,isp,org,as,query", timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data['status'] == 'fail': return jsonify({"error": "IP bulunamadı"}), 404
            
            result = {
                "ip": data['query'],
                "location": f"{data.get('city')}, {data.get('country')}",
                "isp": data.get('isp'),
                "org": data.get('org'),
                "as": data.get('as')
            }
            set_cache(f"ip_{ip_addr}", result)
            return jsonify(result)

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

@app.route('/api/whois', methods=['GET'])
@limiter.limit("10 per minute")
def get_whois():
    """Domain için WHOIS bilgilerini çeker (Gelişmiş hata yönetimi ve önbellek)."""
    domain = request.args.get('domain', '').strip().lower()
    if not domain: return jsonify({"error": "Domain gerekli"}), 400
    
    # WHOIS sorgularında kullanıcı talebiyle önbellek kaldırıldı

    import whois
    try:
        # Bazı sistemlerde whois komutu eksik olabilir, kütüphane bunu yönetir
        w = whois.whois(domain)
        
        if not w or not any(w.values()):
            return jsonify({"error": "Whois kaydı bulunamadı veya domain geçersiz."}), 404

        # Tarih formatlarını düzelt
        def format_date(d):
            if not d: return "Bilinmiyor"
            if isinstance(d, list): d = d[0]
            try:
                return d.strftime('%Y-%m-%d %H:%M:%S') if hasattr(d, 'strftime') else str(d)
            except:
                return str(d)

        # Name Server temizleme
        ns_list = []
        if w.name_servers:
            if isinstance(w.name_servers, list):
                ns_list = [str(ns).lower() for ns in w.name_servers if ns]
            else:
                ns_list = [str(w.name_servers).lower()]

        result = {
            "domain": domain,
            "registrar": (w.registrar[0] if isinstance(w.registrar, list) else w.registrar) or "Bilinmiyor",
            "creation_date": format_date(w.get('creation_date')),
            "expiration_date": format_date(w.get('expiration_date')),
            "name_servers": sorted(list(set(ns_list))),
            "status": (w.status[0] if isinstance(w.status, list) else w.status) or "Bilinmiyor"
        }
        set_cache(f"whois_{domain}", result)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Whois Hatası ({domain}): {e}")
        return jsonify({"error": f"Whois bilgisi alınamadı: {str(e)}"}), 500

@app.route('/api/analyze_all', methods=['POST'])
@limiter.limit("2 per hour")
def trigger_bulk_analysis():
    """Arka planda bekleyen tüm haberleri analiz eder."""
    scheduler.add_job(func=process_missing_analysis, trigger="date")
    return jsonify({"message": "Toplu analiz süreci başlatıldı."})

@app.route('/api/subdomains', methods=['GET'])
@limiter.limit("10 per minute")
def get_subdomains():
    """crt.sh üzerinden pasif subdomain keşfi (Timeout ve Hata Yönetimi)."""
    domain = request.args.get('domain', '').strip().lower()
    if not domain: return jsonify({"error": "Domain gerekli"}), 400
    
    # Subdomain keşfinde kullanıcı talebiyle önbellek kaldırıldı

    try:
        # crt.sh bazen yavaş olabilir, timeout ekliyoruz
        url = f"https://crt.sh/?q=%25.{domain}&output=json"
        res = requests.get(url, timeout=20)
        
        if res.status_code == 200:
            try:
                data = res.json()
            except:
                return jsonify({"error": "crt.sh verisi okunamadı."}), 502

            if not data:
                return jsonify({"error": f"{domain} için hiçbir sertifika kaydı bulunamadı."}), 404

            # Alt alan adlarını ayıkla ve temizle
            subs = set()
            for entry in data:
                name = entry.get('name_value', '')
                # Çoklu satır (wildcard vb) olanları ayır
                for n in name.split('\n'):
                    n = n.strip().lower()
                    if n.endswith(domain) and n != domain and '*' not in n:
                        subs.add(n)
            
            if not subs:
                return jsonify({"error": "Alt alan adı tespit edilemedi (Sadece ana domain kayıtlı olabilir)."}), 404

            result = {
                "domain": domain, 
                "subdomains": sorted(list(subs))[:100] # İlk 100 tanesini sınırla
            }
            set_cache(f"subs_{domain}", result)
            return jsonify(result)
        return jsonify({"error": f"crt.sh servisi hata döndürdü: {res.status_code}"}), 502
    except requests.exceptions.Timeout:
        return jsonify({"error": "Sorgu zaman aşımına uğradı (crt.sh çok yavaş). Lütfen birazdan tekrar deneyin."}), 504
    except Exception as e:
        logger.error(f"Subdomain Hatası ({domain}): {e}")
        return jsonify({"error": "Bağlantı hatası veya geçersiz veri."}), 500

if __name__ == '__main__':
    # Veritabanını kontrol et ve gerekirse tabloları/sütunları oluştur
    init_db()
    
    logger.info("🚀 SentinelAi Sunucusu Başlatılıyor...")
    app.run(host='0.0.0.0', port=5000, debug=True)

