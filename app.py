import os
import requests
import sqlite3
import subprocess
import io
import re
from flask import Flask, render_template, jsonify, request, send_file
from dotenv import load_dotenv
from core.fetcher import NewsSentinel
from core.brain import SentinelBrain
from apscheduler.schedulers.background import BackgroundScheduler
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
DB_PATH = "/app/data/sentinel.db"
sentinel_fetcher = NewsSentinel()
sentinel_brain = SentinelBrain()

def run_fetcher():
    try:
        # Mevcut dosyanın bulunduğu ana dizini bul (/app)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"📡 Haberler taranıyor (Dizin: {base_dir})...")
        
        # Python'un ana dizinde olduğunu varsayarak core/fetcher.py'yi çalıştır
        subprocess.run(
            ["python3", "core/fetcher.py"], 
            cwd=base_dir, # Çalışma dizinini /app olarak sabitle
            check=True
        )
        print("✅ Tarama tamamlandı.")
    except Exception as e:
        print(f"❌ Haber çekme hatası: {e}")

# -- Veritabanı oluşturma

def init_db():
    # Klasör kontrolü
    if not os.path.exists('data'):
        os.makedirs('data')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Golden Version Tablo Yapısı
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            link TEXT UNIQUE,
            published TEXT,
            source TEXT,
            ai_analysis TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ Veritabanı başarıyla doğrulandı/oluşturuldu.")

# Uygulama nesnesi (app = Flask(__name__)) oluşturulduktan hemen sonra çağır:
init_db()
run_fetcher()


# --- PDF İÇİN GÜVENLİ METİN TEMİZLEME (KESİN ÇÖZÜM) ---
def safe_pdf_text(text):
    if not text: return ""
    # Sadece PDF'in (latin-1) desteklediği karakterleri tut, diğerlerini (emoji vb.) sil
    return "".join(c for c in str(text) if ord(c) < 256)

# --- PDF SINIFI ---
class SentinelPDF(FPDF):
    def header(self):
        self.set_font("helvetica", "B", 15)
        self.cell(0, 10, "SENTINEL AI - SIBER GUVENLIK RAPORU", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.cell(0, 10, f"Sayfa {self.page_no()} | {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")

# --- SCHEDULER (Haberlerin Akması İçin) ---
def scheduled_scan():
    print("--- Otomatik Tarama Başlatıldı ---")
    try:
        new_stories = sentinel_fetcher.scan_news()
        # Otomatik analiz ve bildirim işlemleri buraya eklenebilir
    except Exception as e:
        print(f"Tarama Hatası: {e}")

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(func=scheduled_scan, trigger="interval", minutes=5)
scheduler.start()

# --- AI Yönetim Sınıfı (Mevcut kodun üst kısmına ekle) ---
class AIManager:
    def __init__(self):
        self.keys = {
            "gemini": os.getenv('GEMINI_API_KEY'),
            "groq": os.getenv('GROQ_API_KEY'),
            "mistral": os.getenv('MISTRAL_API_KEY')
        }
        self.order = ["gemini", "groq", "mistral"]

    def analyze_with_name(self, prompt):
        for service in self.order:
            key = self.keys.get(service)
            if not key or key == "" or key == "disable": # disable kontrolü eklendi
                continue
            try:
                if service == "gemini":
                    from google import genai
                    client = genai.Client(api_key=key)
                    res = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                    return res.text, "gemini"
                
                elif service == "groq":
                    from groq import Groq
                    client = Groq(api_key=key)
                    res = client.chat.completions.create(
                        model="llama-3.1-70b-versatile",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    return res.choices[0].message.content, "groq"

                elif service == "mistral":
                    from mistralai import Mistral
                    client = Mistral(api_key=key)
                    res = client.chat.complete(model="mistral-large-latest", messages=[{"role": "user", "content": prompt}])
                    return res.choices[0].message.content, "mistral"
            except Exception as e:
                print(f"⚠️ {service.upper()} failover tetiklendi: {e}")
                continue
        
        # Hata durumunda bile 2 değer döndürerek "unpack" hatasını engelliyoruz
        return "Tüm AI servisleri başarısız oldu veya kotalar doldu.", "sistem"

ai_manager = AIManager()

# --- Güncellenmiş Analiz Rotası ---

@app.route('/api/analyze', methods=['POST'])
def analyze_news():
    data = request.json
    title, link = data.get('title'), data.get('link')
    prompt = f"Siber güvenlik tehdit analizi yap. Tehdit seviyesini KRITIK, ORTA veya DUSUK olarak belirt. Haber: {title}"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT ai_analysis FROM news WHERE link = ?", (link,))
    row = cursor.fetchone()
    if row and row[0]:
        conn.close()
        return jsonify({"analysis": row[0]})

    # Unpack hatası artık alınmayacak çünkü fonksiyon hep 2 değer dönecek
    analysis_text, model_name = ai_manager.analyze_with_name(prompt)
    
    # Model ismini metnin başına ekle
    full_response = f"[{model_name.upper()}] {analysis_text}"

    cursor.execute("UPDATE news SET ai_analysis = ? WHERE link = ?", (full_response, link))
    conn.commit()
    conn.close()
    
    return jsonify({"analysis": full_response})

# Son güncelleme bilgisini frontend'e basmak için statik bir zaman veya DB'den son haber zamanı:
@app.route('/api/status')
def get_status():
    return jsonify({
        "last_sync": datetime.now().strftime("%H:%M:%S"),
        "active_models": [k for k, v in ai_manager.keys.items() if v and v != "disable"]
    })


# --- ANA ROTAlar ---

@app.route('/')
def index():
    return render_template('index.html')



@app.route('/api/stats')
def get_stats():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT source, COUNT(*) as count FROM news GROUP BY source")
        source_stats = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({"sources": source_stats})
    except: return jsonify({"sources": []})



@app.route('/api/report/single', methods=['POST'])
def report_single():
    data = request.json
    title = safe_pdf_text(data.get('title'))
    content = safe_pdf_text(data.get('content'))
    
    pdf = SentinelPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 12)
    pdf.multi_cell(0, 10, f"ANALIZ: {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)
    pdf.set_font("helvetica", "", 10)
    pdf.multi_cell(0, 7, content)
    
    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="analiz_raporu.pdf", mimetype="application/pdf")

# --- app.py içindeki ilgili rotaların güncellenmiş hali ---

@app.route('/api/news')
def get_news():
    try:
        page = int(request.args.get('page', 1))
        per_page = 10
        offset = (page - 1) * per_page
        search_query = request.args.get('search', '')

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if search_query:
            cursor.execute("SELECT * FROM news WHERE title LIKE ? OR source LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?", 
                           (f'%{search_query}%', f'%{search_query}%', per_page, offset))
        else:
            cursor.execute("SELECT * FROM news ORDER BY created_at DESC LIMIT ? OFFSET ?", (per_page, offset))
        
        news_list = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(news_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/report/weekly')
def report_weekly():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        last_week = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        # PDF içeriği için AI analizlerini de çekiyoruz
        cursor.execute("SELECT title, source, published, ai_analysis FROM news WHERE created_at >= ? ORDER BY created_at DESC", (last_week,))
        news = cursor.fetchall()
        conn.close()

        pdf = SentinelPDF()
        pdf.add_page()
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(0, 10, "HAFTALIK TEHDIT VE ANALIZ RAPORU", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(10)
        
        for item in news:
            # Haber Başlığı
            pdf.set_font("helvetica", "B", 11)
            pdf.set_text_color(59, 130, 246) # Mavi tonu
            clean_title = safe_pdf_text(item['title'])
            pdf.multi_cell(0, 7, f"> {clean_title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            # Meta Bilgiler
            pdf.set_font("helvetica", "I", 8)
            pdf.set_text_color(128, 128, 128)
            pdf.cell(0, 5, f"Kaynak: {item['source']} | Tarih: {item['published']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            # AI Analizi (Eğer varsa)
            if item['ai_analysis']:
                pdf.ln(2)
                pdf.set_font("helvetica", "", 9)
                pdf.set_text_color(200, 200, 200) # Açık gri
                pdf.set_fill_color(30, 35, 40) # Koyu arka plan efekti
                analysis_text = safe_pdf_text(item['ai_analysis'])
                pdf.multi_cell(0, 6, f"AI Analizi: {analysis_text}", fill=False)
            
            pdf.ln(8)
            pdf.set_text_color(0, 0, 0) # Rengi sıfırla
            if pdf.get_y() > 240: pdf.add_page()

        output = io.BytesIO()
        pdf.output(output)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name="Sentinel_Haftalik_Analiz.pdf", mimetype="application/pdf")
    except Exception as e:
        return f"Rapor hatası: {str(e)}", 500

@app.route('/api/tool/cve', methods=['POST'])
def tool_cve():
    cve_id = request.json.get('cve_id')
    prompt = f"{cve_id} kodlu zafiyet hakkında teknik analiz, etkilenen sistemler ve çözüm önerileri sun."
    analysis = sentinel_brain.analyze_incident(prompt)
    return jsonify({"result": analysis})

@app.route('/api/tool/ip', methods=['POST'])
def tool_ip():
    ip_addr = request.json.get('ip')
    try:
        response = requests.get(f"http://ip-api.com/json/{ip_addr}", timeout=10)
        return jsonify(response.json())
    except: return jsonify({"status": "fail"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
