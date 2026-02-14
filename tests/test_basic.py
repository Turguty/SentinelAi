import pytest
import os
import sys

# Proje kök dizinini ekle
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from core.ai_manager import AIManager

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
    res = client.get('/api/cve?id=INVALID-CVE')
    assert res.status_code == 400
    assert b'format' in res.data

def test_ip_validation(client):
    """Eksik IP adresi girildiğinde hata döndüğünü kontrol eder."""
    res = client.get('/api/ip?ip=')
    assert res.status_code == 400
