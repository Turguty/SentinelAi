import pytest
import os
import sys
import json
from unittest.mock import MagicMock, patch

# Proje kök dizinini ekle
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from core.ai_manager import AIManager
from core.fetcher import parse_ai_json_to_text

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_index_page(client):
    """Ana sayfanın başarıyla yüklendiğini kontrol eder."""
    res = client.get('/')
    assert res.status_code == 200
    assert b'SENTINEL' in res.data

def test_api_status(client):
    """AI durum API'sinin doğru formatta döndüğünü kontrol eder."""
    res = client.get('/api/ai_status')
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, dict)
    assert 'gemini' in data

def test_ai_manager_init():
    """AI Manager'ın doğru şekilde başlatıldığını kontrol eder."""
    ai = AIManager()
    assert hasattr(ai, 'keys')
    assert ai.order[0] == 'gemini'

def test_cve_validation(client):
    """Geçersiz CVE formatı girildiğinde hata döndüğünü kontrol eder."""
    res = client.get('/api/cve?id=INVALID')
    assert res.status_code == 400
    # Hata mesajı tam olarak 'format' içermeyebilir, 'error' keyini kontrol et
    assert b'error' in res.data or b'format' in res.data

def test_ip_validation(client):
    """Eksik IP adresi girildiğinde hata döndüğünü kontrol eder."""
    res = client.get('/api/ip?ip=')
    assert res.status_code == 400

# --- YENİ TESTLER ---

def test_fetcher_parse_ai_json():
    """parse_ai_json_to_text fonksiyonunun doğru dönüştürme yaptığını test eder."""
    sample_json = {
        "threat_level": "HIGH",
        "category": "Ransomware",
        "summary": "This is a test summary.",
        "technical_details": "IOC: 127.0.0.1"
    }
    result = parse_ai_json_to_text(sample_json)
    assert "TEHDIT SEVIYESI: [HIGH]" in result
    assert "KATEGORI: [Ransomware]" in result
    assert "Özet: This is a test summary." in result

def test_ai_manager_analyze_json():
    """analyze_json metodunun JSON stringlerini başarıyla parse ettiğini test eder."""
    ai = AIManager()
    
    # Mock analyze method
    with patch.object(ai, 'analyze', return_value='```json\n{"key": "value"}\n```') as mock_analyze:
        result = ai.analyze_json("dummy prompt", system_prompt="sys")
        assert result == {"key": "value"}
        mock_analyze.assert_called_once()
        
    # Bad JSON handling
    with patch.object(ai, 'analyze', return_value='This is not JSON') as mock_analyze_fail:
        result_fail = ai.analyze_json("dummy prompt", system_prompt="sys")
        assert result_fail is None
