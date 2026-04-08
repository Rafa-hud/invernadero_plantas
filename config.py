# config.py
import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Configuración básica
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave-secreta-muy-segura-plantas-2026'
    
    # Base de datos MongoDB Atlas (Actualizada)
    # Se utiliza tu URI de Atlas por defecto, pero se prefiere la variable de entorno en producción
    MONGO_URI = os.environ.get('MONGO_URI') or "mongodb+srv://admin:Emmanuel123@cluster0.cerffq3.mongodb.net/?appName=Cluster0"
    
    # Configuración de sesión
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=60)
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # ========== CONFIGURACIÓN PARA RESPALDOS ==========
    BACKUP_DIR = os.path.join(basedir, 'backups')
    BACKUP_RETENTION_DAYS = 30
    BACKUP_TYPES = ['completo', 'diferencial', 'minima_modificacion']
    MAX_BACKUP_SIZE_MB = 50
    COMPRESS_BACKUPS = True
    COMPRESSION_LEVEL = 9
    VERIFY_CHECKSUM = True
    VERIFY_FILE_SIZE = True
    AUTO_BACKUP_INTERVAL = 24
    
    # Notificaciones y Medios
    SEND_BACKUP_NOTIFICATIONS = False
    NOTIFICATION_EMAIL = os.environ.get('NOTIFICATION_EMAIL', '')
    STORAGE_MEDIA = ['local', 'usb']
    
    # Configuración de correo
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    
    @staticmethod
    def init_app(app):
        """Inicializar la aplicación con configuraciones necesarias"""
        directories = [Config.BACKUP_DIR, os.path.join(basedir, 'logs')]
        
        for directory in directories:
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory)
                    print(f"✅ Directorio creado: {directory}")
                except Exception as e:
                    print(f"⚠️  Error al crear directorio {directory}: {str(e)}")
        
        # Mostrar configuración de MongoDB de forma segura
        print(f"📋 Configuración MongoDB:")
        uri_raw = Config.MONGO_URI
        try:
            # Lógica mejorada para ocultar contraseña en URIs de Atlas (mongodb+srv)
            if "@" in uri_raw:
                parte_inicial, resto = uri_raw.split("://")
                credenciales, host = resto.split("@")
                uri_segura = f"{parte_inicial}://***:***@{host.split('?')[0]}..."
                print(f"   URI: {uri_segura}")
            else:
                print(f"   URI: {uri_raw}")
        except Exception:
            print("   URI: [Formato de URI no reconocido para impresión segura]")

class DevelopmentConfig(Config):
    DEBUG = True
    VERIFY_CHECKSUM = False
    SEND_BACKUP_NOTIFICATIONS = False

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    VERIFY_CHECKSUM = True
    SEND_BACKUP_NOTIFICATIONS = True

class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    # URI de prueba (puedes cambiarla a una DB local o una base 'test' en Atlas)
    MONGO_URI = os.environ.get('TEST_MONGO_URI') or 'mongodb://localhost:27017/test_gestion_plantas'
    BACKUP_DIR = os.path.join(basedir, 'test_backups')

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}