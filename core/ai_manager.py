import os
import time
import requests
from dotenv import load_dotenv
from google import genai
from groq import Groq
from mistralai import Mistral

# .env dosyasındaki API anahtarlarını yükle
load_dotenv()

class AIManager:
    """
    SentinelAi'nın beyin motoru: Birden fazla AI servisini (Gemini, Groq, Mistral vb.) 
    yedekli (fallback) ve hata toleranslı şekilde yönetir.
    """
    def __init__(self):
        """
        AI servisleri için anahtarları hazırlar ve başlangıç durumlarını (cooldown vb.) ayarlar.
        """
        self.keys = {
            "gemini": os.getenv('GEMINI_API_KEY'),
            "groq": os.getenv('GROQ_API_KEY'),
            "mistral": os.getenv('MISTRAL_API_KEY'),
            "openrouter": os.getenv('OPENROUTER_API_KEY'),
            "huggingface": os.getenv('HUGGINGFACE_API_KEY')
        }
        # Deneme önceliği sırası
        self.order = ["gemini", "groq", "mistral", "openrouter", "huggingface"]
        # Hatalı servislerin bekleme süresi takibi
        self.cooldowns = {service: 0 for service in self.order}
        self.cooldown_duration = 300  # 5 dakika soğuma süresi

    def get_status(self):
        """
        Her bir AI servisinin mevcut durumunu (aktif, soğumada, anahtar eksik) döner.
        Dashbord üzerindeki durum çubuğu bu veriyi kullanır.
        """
        current_time = time.time()
        status = {}
        for service in self.order:
            if not self.keys.get(service) and service != "huggingface":
                status[service] = "no_key"
            elif current_time < self.cooldowns[service]:
                status[service] = "cooldown"
            else:
                status[service] = "active"
        return status

    def analyze(self, prompt):
        """
        Verilen metni (haber, CVE vb.) mevcut AI servislerini sırayla deneyerek analiz eder.
        Kota aşımı veya hata durumunda otomatik olarak bir sonraki servise geçer.
        """
        current_time = time.time()
        for service in self.order:
            # Anahtar kontrolü ve soğuma süresi denetimi
            if not self.keys.get(service) and service != "huggingface": continue
            if current_time < self.cooldowns[service]: continue
            
            try:
                # Servisler arası çok hızlı geçişi önlemek için kısa mola
                time.sleep(1.5) 
                
                print(f"🤖 AI Deneniyor: {service.upper()}")
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
                print(f"⚠️ {service.upper()} Hatası: {str(e)}")
                # Hata alan servisi geçici olarak engelle (5 dk)
                self.cooldowns[service] = current_time + self.cooldown_duration
                continue

        return "HATA: Tüm AI servisleri şu an ulaşılamaz durumda."

    def _call_gemini(self, prompt):
        """Google Gemini 2.0 API üzerinden analiz yapar."""
        try:
            client = genai.Client(api_key=self.keys["gemini"])
            return client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
        except Exception as e:
            return f"HATA: {str(e)}"

    def _call_groq(self, prompt):
        """Groq (Llama-3.3) API üzerinden yüksek hızlı analiz yapar."""
        try:
            client = Groq(api_key=self.keys["groq"])
            res = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}])
            return res.choices[0].message.content
        except Exception as e:
            return f"HATA: {str(e)}"

    def _call_mistral(self, prompt):
        """Mistral AI (Large-Latest) üzerinden analiz yapar."""
        try:
            client = Mistral(api_key=self.keys["mistral"])
            res = client.chat.complete(model="mistral-large-latest", messages=[{"role": "user", "content": prompt}])
            return res.choices[0].message.content
        except Exception as e:
            return f"HATA: {str(e)}"

    def _call_openrouter(self, prompt):
        """OpenRouter üzerinden belirlenen modelleri (Gemini vb) çağıran yedek kanal."""
        try:
            headers = {"Authorization": f"Bearer {self.keys['openrouter']}", "Content-Type": "application/json"}
            payload = {"model": "google/gemini-2.0-flash-001", "messages": [{"role": "user", "content": prompt}]}
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=20)
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content']
            return f"HATA: HTTP {res.status_code}"
        except Exception as e:
            return f"HATA: {str(e)}"

    def _call_huggingface(self, prompt):
        """Hugging Face Inference API üzerinden (Qwen vb) açık kaynak modelleri çağırır."""
        try:
            model = "Qwen/Qwen2.5-72B-Instruct"
            url = f"https://api-inference.huggingface.co/models/{model}"
            headers = {"Content-Type": "application/json"}
            if self.keys['huggingface']: headers["Authorization"] = f"Bearer {self.keys['huggingface']}"
            payload = {"inputs": prompt, "parameters": {"max_new_tokens": 500}}
            res = requests.post(url, headers=headers, json=payload, timeout=20)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list) and 'generated_text' in data[0]: return data[0]['generated_text']
                return str(data)
            return f"HATA: HTTP {res.status_code}"
        except Exception as e:
            return f"HATA: {str(e)}"
