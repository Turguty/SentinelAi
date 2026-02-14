import requests
import os
import json

class SentinelBrain:
    def __init__(self):
        # .env dosyasından API anahtarını alıyoruz
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        
        # 404 HATASI ÇÖZÜMÜ:
        # 'exp' (experimental) takılı modeller bazen listeden kalkabiliyor.
        # Şu an OpenRouter'da en kararlı ücretsiz modellerden birini kullanalım:
        self.model = "google/gemini-2.0-flash-001" # veya "google/gemini-2.0-pro-exp-02-05:free"

    def analyze_incident(self, news_title):
        """
        Haber başlığını alır ve OpenRouter üzerinden (Gemini-2.0-Flash) teknik analizini yapar.
        Analiz şunları içerir: Tehdit seviyesi, teknik maddeler ve önerilen aksiyonlar.
        """
        if not self.api_key:
            return "Sistem Hatası: .env dosyasında 'OPENROUTER_API_KEY' bulunamadı."

        # Prompt hazırlığı: Siber güvenlik uzmanı rolünde analiz ister
        prompt = (
            f"Sen bir siber güvenlik uzmanısın. Şu haberi analiz et:\n\n"
            f"Haber: {news_title}\n\n"
            f"Lütfen şunları sağla:\n"
            f"- Tehdit Seviyesi\n"
            f"- 3 kısa teknik madde\n"
            f"- Önerilen aksiyon\n"
            f"Cevap dili: Türkçe"
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5000"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Sen kıdemli bir siber güvenlik analistisin."},
                {"role": "user", "content": prompt}
            ]
        }

        try:
            response = requests.post(
                self.api_url, 
                headers=headers, 
                data=json.dumps(payload),
                timeout=25
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'choices' in result and len(result['choices']) > 0:
                    return result['choices'][0]['message']['content']
                return "AI Hatası: API'den veri döndü ancak içerik boş."
            
            # Hata kodlarını detaylı verelim
            return f"AI Servis Hatası: {response.status_code} - {response.text[:150]}"
                
        except Exception as e:
            return f"Bağlantı Hatası: {str(e)}"
