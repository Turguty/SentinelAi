import os
import sqlite3
import time
import requests
from flask import Flask, render_template, request, jsonify
from core.ai_manager import AIManager

app = Flask(__name__)
DB_PATH = 'data/sentinel.db'
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
