import feedparser
import sqlite3
import os
import json
from datetime import datetime

class NewsSentinel:
    def __init__(self):
        self.db_path = "data/sentinel.db"
        self.sources_path = "sources.json"
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                link TEXT UNIQUE,
                source TEXT,
                published TEXT,
                ai_analysis TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def scan_news(self):
        new_findings = []
        if not os.path.exists(self.sources_path):
            print("Hata: sources.json dosyasi bulunamadi.")
            return []

        with open(self.sources_path, 'r', encoding='utf-8') as f:
            sources = json.load(f)['sources']

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for source in sources:
            if not source.get('active', True): continue
            try:
                # Haber sayisi 20'ye cikarildi
                feed = feedparser.parse(source['url'])
                for entry in feed.entries[:20]:
                    title = entry.title
                    link = entry.link
                    published = entry.get("published", datetime.now().strftime("%Y-%m-%d %H:%M"))
                    try:
                        cursor.execute(
                            "INSERT INTO news (title, link, source, published) VALUES (?, ?, ?, ?)",
                            (title, link, source['name'], published)
                        )
                        conn.commit()
                        new_findings.append({"title": title, "link": link})
                    except sqlite3.IntegrityError:
                        continue
            except Exception as e:
                print(f"Kaynak tarama hatasi ({source['name']}): {e}")
        conn.close()
        return new_findings
