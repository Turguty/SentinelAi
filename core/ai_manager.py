import os
import time
import requests
import json
import re
from dotenv import load_dotenv
from google import genai
from groq import Groq
from mistralai import Mistral
from core.logger import setup_logger

# Loglama kurulumu
logger = setup_logger("AIManager")

# .env dosyasındaki API anahtarlarını yükle
load_dotenv()

class AIManager:
    """
    SentinelAi'nın beyin motoru: Birden fazla AI servisini (Gemini, Groq, Mistral vb.) 
    yedekli (fallback) ve hata toleranslı şekilde yönetir.
    """
    # Sınıf seviyesinde paylaşımlı durum takibi (Background task ve App arası senkronizasyon için)
    _shared_cooldowns = {}

    def __init__(self):
        """
        AI servisleri için anahtarları hazırlar ve başlangıç durumlarını ayarlar.
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
        
        # Paylaşımlı cooldown sözlüğünü ilk kez oluştur
        if not AIManager._shared_cooldowns:
            AIManager._shared_cooldowns = {service: 0 for service in self.order}
        
        self.cooldown_duration = 300  # 5 dakika soğuma süresi

    def get_status(self):
        """
        Her bir AI servisinin mevcut durumunu (aktif, soğumada, anahtar eksik) döner.
        """
        current_time = time.time()
        status = {}
        for service in self.order:
            if not self.keys.get(service) and service != "huggingface":
                status[service] = "no_key"
            elif current_time < AIManager._shared_cooldowns.get(service, 0):
                status[service] = "cooldown"
            else:
                status[service] = "active"
        return status

    def analyze(self, prompt, use_load_balance=False, system_prompt=None):
        """
        Verilen metni mevcut AI servislerini deneyerek analiz eder.
        use_load_balance=True ise servisleri sırayla değil, farklı servisleri deneyecek şekilde dağıtır.
        system_prompt opsiyonel olarak eklenebilir.
        """
        current_time = time.time()
        
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\nUser Input:\n{prompt}"

        # Deneme listesini oluştur
        test_order = self.order.copy()
        if use_load_balance:
            # Load balance durumunda önceliği kaydır (basit Round-Robin benzeri)
            shift = int(time.time() % len(self.order))
            test_order = self.order[shift:] + self.order[:shift]

        for service in test_order:
            if not self.keys.get(service) and service != "huggingface": continue
            if current_time < AIManager._shared_cooldowns.get(service, 0): continue
            
            try:
                # Servisler arası çok hızlı geçişi önlemek için kısa mola
                time.sleep(1.0) 
                
                logger.info(f"🤖 AI Deneniyor: {service.upper()}")
                if service == "gemini": result = self._call_gemini(full_prompt)
                elif service == "groq": result = self._call_groq(full_prompt)
                elif service == "mistral": result = self._call_mistral(full_prompt)
                elif service == "openrouter": result = self._call_openrouter(full_prompt)
                elif service == "huggingface": result = self._call_huggingface(full_prompt)
                
                if result and "HATA:" not in result:
                    logger.info(f"✅ {service.upper()} başarılı.")
                    return result # Raw result döndür, imza işini çağıran yere bırakabiliriz veya format json ise dokunma
                else:
                    raise Exception(result)

            except Exception as e:
                logger.warning(f"⚠️ {service.upper()} Hatası: {str(e)}")
                # Hata alan servisi paylaşımlı durumda engelle
                AIManager._shared_cooldowns[service] = current_time + self.cooldown_duration
                continue

        logger.error("❌ Tüm AI servisleri şu an ulaşılamaz durumda.")
        return "HATA: Tüm AI servisleri şu an ulaşılamaz durumda."

    def analyze_json(self, prompt, system_prompt):
        """
        AI çıktısını JSON olarak almaya çalışır ve parse eder.
        Geriye dict döner veya None döner.
        """
        raw_result = self.analyze(prompt, system_prompt=system_prompt)
        
        if raw_result and "HATA:" in raw_result:
            return None

        # JSON temizleme ve parse etme
        try:
            # Markdown code block temizliği
            cleaned = re.sub(r"```json\s*|\s*```", "", raw_result, flags=re.IGNORECASE).strip()
            # Bazen başında/sonunda yazı olabilir, ilk { ve son } arasını al
            start = cleaned.find('{')
            end = cleaned.rfind('}')
            if start != -1 and end != -1:
                cleaned = cleaned[start:end+1]
            
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parse Hatası: {e} | Raw: {raw_result[:100]}...")
            return None


    def _call_gemini(self, prompt):
        """Google Gemini 2.0 API üzerinden analiz yapar."""
        try:
            client = genai.Client(api_key=self.keys["gemini"])
            # Gemini 2.0 Flash JSON modu destekler ama basit text generation kullanalım şimdilik
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
        """OpenRouter üzerinden belirlenen modelleri çağıran yedek kanal."""
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
        """Hugging Face Inference API üzerinden açık kaynak modelleri çağırır."""
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

