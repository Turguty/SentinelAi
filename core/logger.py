import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(name):
    """
    Sistem genelinde kullanılacak log yapılandırmasını oluşturur.
    Loglar hem konsola hem de 'data/sentinel.log' dosyasına yazılır.
    """
    if not os.path.exists('data'):
        os.makedirs('data')

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Log formatı: Zaman - Modül - Seviye - Mesaj
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Dosya Loglayıcı (Maksimum 5MB, 3 yedek dosya)
    file_handler = RotatingFileHandler('data/sentinel.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    # Konsol Loglayıcı
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Logger'a işleyicileri ekle (Eğer daha önce eklenmemişse)
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger
