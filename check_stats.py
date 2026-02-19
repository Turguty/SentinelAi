import sqlite3

conn = sqlite3.connect('data/sentinel.db')
cursor = conn.cursor()

cursor.execute('SELECT category, COUNT(*) FROM news GROUP BY category ORDER BY COUNT(*) DESC')

print('\n=== KATEGORI DAĞILIMI ===\n')
total = 0
for row in cursor.fetchall():
    cat = row[0] if row[0] else "Kategorisiz"
    count = row[1]
    print(f'{cat[:20]:20} : {count:3} haber')
    total += count

print(f'\n{"="*30}')
print(f'{"TOPLAM":20} : {total:3} haber')

conn.close()
