import sqlite3

conn = sqlite3.connect('data/sentinel.db')
cursor = conn.cursor()

valid_categories = ['Malware', 'Phishing', 'Ransomware', 'Vulnerability', 'Breach', 'DDoS', 'APT', 'Data Leak', 'General']

cursor.execute('SELECT id, category FROM news')
rows = cursor.fetchall()

fixed = 0
for row_id, cat in rows:
    if cat and cat not in valid_categories:
        cursor.execute('UPDATE news SET category=? WHERE id=?', ('General', row_id))
        fixed += 1
        print(f'Düzeltildi: ID {row_id} -> General (eski: {cat[:50]}...)')

conn.commit()
print(f'\n✅ Toplam düzeltilen: {fixed} haber')

conn.close()
