import os
import sqlite3
import time
import requests
from flask import Flask, render_template, request, jsonify
from google import genai
from groq import Groq
from mistralai import Mistral

app = Flask(__name__)
DB_PATH = 'data/sentinel.db'

# AI Manager Sınıfı: Farklı AI API'lerini (Gemini, Groq, Mistral, OpenRouter, HuggingFace) yedekli yönetir.
class AIManager:
    def __init__(self):
        """
        AI servisleri için API anahtarlarını hazırlar ve hata durumlarını takip eder.
        """
        self.keys = {
            "gemini": os.getenv('GEMINI_API_KEY'),
            "groq": os.getenv('GROQ_API_KEY'),
            "mistral": os.getenv('MISTRAL_API_KEY'),
            "openrouter": os.getenv('OPENROUTER_API_KEY'),
            "huggingface": os.getenv('HUGGINGFACE_API_KEY')
        }
        # Servislerin deneneceği öncelik sırası
        self.order = ["gemini", "groq", "mistral", "openrouter", "huggingface"]
        # Hata alan servisleri geçici olarak devre dışı bırakmak için cooldown takibi
        self.cooldowns = {service: 0 for service in self.order}
        self.cooldown_duration = 300  # 5 dakika (saniye cinsinden)

    def analyze(self, prompt):
        """
        Belirlenen sırayla AI servislerini çağırır. Kota/Hata durumunda bir sonrakine geçer.
        """
        current_time = time.time()
        
        for service in self.order:
            # API anahtarı yoksa veya servis cooldown (soğuma) süresindeyse atla
            if not self.keys.get(service) and service != "huggingface": continue
            if current_time < self.cooldowns[service]:
                print(f"ℹ️ {service.upper()} soğuma modunda, atlanıyor...")
                continue

            try:
                print(f"🤖 Deneniyor: {service.upper()}")
                if service == "gemini": result = self._call_gemini(prompt)
                elif service == "groq": result = self._call_groq(prompt)
                elif service == "mistral": result = self._call_mistral(prompt)
                elif service == "openrouter": result = self._call_openrouter(prompt)
                elif service == "huggingface": result = self._call_huggingface(prompt)
                
                if result and "HATA:" not in result:
                    return result
                else:
                    raise Exception(result)

            except Exception as e:
                print(f"⚠️ {service.upper()} hatası: {str(e)}")
                # Kota hatası veya genel hata durumunda servisi cooldown listesine al
                self.cooldowns[service] = current_time + self.cooldown_duration
                continue

        return "HATA: Tüm AI servislerinin kotası doldu veya servisler şu an ulaşılamaz durumda."

    def _call_gemini(self, prompt):
        """Google Gemini API'sini kullanarak içerik üretir."""
        try:
            client = genai.Client(api_key=self.keys["gemini"])
            return client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
        except Exception as e:
            return f"HATA: Gemini - {str(e)}"

    def _call_groq(self, prompt):
        """Groq (Llama) API'sini kullanarak içerik üretir."""
        try:
            client = Groq(api_key=self.keys["groq"])
            res = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}])
            return res.choices[0].message.content
        except Exception as e:
            return f"HATA: Groq - {str(e)}"

    def _call_mistral(self, prompt):
        """Mistral AI API'sini kullanarak içerik üretir."""
        try:
            client = Mistral(api_key=self.keys["mistral"])
            res = client.chat.complete(model="mistral-large-latest", messages=[{"role": "user", "content": prompt}])
            return res.choices[0].message.content
        except Exception as e:
            return f"HATA: Mistral - {str(e)}"

    def _call_openrouter(self, prompt):
        """OpenRouter üzerinden belirlenen modeli çağırır."""
        try:
            headers = {"Authorization": f"Bearer {self.keys['openrouter']}", "Content-Type": "application/json"}
            payload = {
                "model": "google/gemini-2.0-flash-001",
                "messages": [{"role": "user", "content": prompt}]
            }
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=20)
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content']
            return f"HATA: OpenRouter HTTP {res.status_code}"
        except Exception as e:
            return f"HATA: OpenRouter - {str(e)}"

    def _call_huggingface(self, prompt):
        """Hugging Face Inference API üzerinden açık kaynaklı modelleri çağırır."""
        try:
            # model = "HuggingFaceH4/zephyr-7b-beta"
            model = "Qwen/Qwen2.5-72B-Instruct"
            url = f"https://api-inference.huggingface.co/models/{model}"
            headers = {"Content-Type": "application/json"}
            if self.keys['huggingface']:
                headers["Authorization"] = f"Bearer {self.keys['huggingface']}"
            
            payload = {"inputs": prompt, "parameters": {"max_new_tokens": 500}}
            res = requests.post(url, headers=headers, json=payload, timeout=20)
            
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list) and 'generated_text' in data[0]:
                    return data[0]['generated_text']
                return str(data)
            return f"HATA: HuggingFace HTTP {res.status_code}"
        except Exception as e:
            return f"HATA: HuggingFace - {str(e)}"

ai_manager = AIManager()

@app.route('/')
def index():
    return render_template('index.html')

# SQLite bağlantı yardımcısı (Kilitlenmeleri önlemek için)
def get_db_connection():
    """Veritabanına bağlanır ve sonuçları sözlük formatında dönecek şekilde ayarlar."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

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
    if existing and existing[0]:
        conn.close()
        return jsonify({"analysis": existing[0]})

    prompt = f"Analizine 'TEHDIT SEVIYESI: [KRITIK/ORTA/DUSUK]' ile başla.\nHaber: {title}\nLink: {link}"
    analysis_result = ai_manager.analyze(prompt)

    if "HATA:" not in analysis_result:
        cursor.execute("UPDATE news SET ai_analysis = ? WHERE link = ?", (analysis_result, link))
        conn.commit()
    conn.close()
    return jsonify({"analysis": analysis_result})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
