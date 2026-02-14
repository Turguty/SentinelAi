# SentinelAi | SOC Dashboard 🛡️

AI destekli, modern ve kompakt bir Siber Güvenlik İstihbarat Paneli. Dünya genelindeki siber güvenlik haberlerini RSS üzerinden toplar ve yapay zeka ile analiz ederek tehdit seviyelerini belirler.

## 🚀 Özellikler
- **Dinamik RSS Tarayıcı:** `sources.json` dosyası üzerinden yönetilebilen, özelleştirilebilir haber kaynakları.
- **Yedekli AI Analizi:** Gemini 2.0, Groq ve Mistral API'leri arasında otomatik geçiş (fallback) mekanizması ile kesintisiz analiz.
- **Modern Arayüz:** Flask tabanlı web arayüzü, Chart.js destekli istatistik grafikleri ve kullanıcı dostu tasarım.
- **Veri Saklama:** Tüm haberler ve analiz sonuçları SQLite veritabanında (`data/sentinel.db`) kalıcı olarak saklanır.
- **Akıllı Arama:** Haberler arasında başlık üzerinden hızlı arama ve sayfalama desteği.

## 🛠️ Kurulum

1. **API Anahtarlarını Hazırlayın:**
   `.env` dosyasını ana dizinde oluşturun ve aşağıdaki anahtarları kendi değerlerinizle doldurun:
   ```env
   GEMINI_API_KEY=your_key
   GROQ_API_KEY=your_key
   MISTRAL_API_KEY=your_key
   ```

2. **Bağımlılıkları Yükleyin:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Verileri Çekin (Opsiyonel):**
   Haberleri manuel olarak hemen çekmek isterseniz:
   ```bash
   python core/fetcher.py
   ```

4. **Uygulamayı Başlatın:**
   ```bash
   python app.py
   ```

5. **Paneli Görüntüleyin:**
   Tarayıcınızda `http://localhost:5000` adresine gidin.

## 📁 Proje Yapısı
- `app.py`: Ana Flask uygulaması ve API uç noktaları.
- `core/fetcher.py`: RSS haberlerini çeken ve veritabanına kaydeden script.
- `core/brain.py`: Alternatif AI analiz motoru (OpenRouter entegrasyonu).
- `data/`: SQLite veritabanı dosyalarının saklandığı klasör.
- `static/`: CSS, JS ve imaj dosyaları.
- `templates/`: HTML şablonları.
- `sources.json`: RSS kaynaklarının listesi.
