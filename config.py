# config.py
import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Configuración básica
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave-secreta-muy-segura-plantas-2026'
    
    # Base de datos MongoDB Atlas (o local)
    # Reemplaza 'gestion_plantas' por el nombre de tu base de datos si es distinto
    MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/gestion_plantas'
    
    # Configuración de sesión
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=60)
    SESSION_COOKIE_SECURE = False  # Cambia a True en producción con HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # ========== CONFIGURACIÓN PARA RESPALDOS ==========
    # Configuración de backup
    BACKUP_DIR = os.path.join(basedir, 'backups')
    BACKUP_RETENTION_DAYS = 30
    
    # Tipos de backup soportados
    BACKUP_TYPES = ['completo', 'diferencial', 'minima_modificacion']
    
    # Tamaño máximo de archivos
    MAX_BACKUP_SIZE_MB = 50
    
    # Configuración de compresión
    COMPRESS_BACKUPS = True
    COMPRESSION_LEVEL = 9
    
    # Verificación de integridad
    VERIFY_CHECKSUM = True
    VERIFY_FILE_SIZE = True
    
    # Frecuencia de backups automáticos
    AUTO_BACKUP_INTERVAL = 24
    
    # Alertas por email
    SEND_BACKUP_NOTIFICATIONS = False
    NOTIFICATION_EMAIL = os.environ.get('NOTIFICATION_EMAIL', '')
    
    # Medios de almacenamiento
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
        # Crear directorios necesarios
        directories = [
            Config.BACKUP_DIR,
            os.path.join(basedir, 'logs')
        ]
        
        for directory in directories:
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory)
                    print(f"✅ Directorio creado: {directory}")
                except Exception as e:
                    print(f"⚠️  Error al crear directorio {directory}: {str(e)}")
        
        # Configurar logging
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        # Imprimir configuración MongoDB limpia (ocultando contraseñas por seguridad)
        print(f"📋 Configuración MongoDB:")
        uri_segura = Config.MONGO_URI
        if '@' in uri_segura:
            # Simple ocultamiento de credenciales para la consola
            protocolo, resto = uri_segura.split('//')
            credenciales, host = resto.split('@')
            uri_segura = f"{protocolo}//***:***@{host}"
            
        print(f"   URI: {uri_segura}")
        print(f"   Carpeta respaldos: {Config.BACKUP_DIR}")


class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True
    
    # Para desarrollo, desactivamos algunas verificaciones estrictas
    VERIFY_CHECKSUM = False
    SEND_BACKUP_NOTIFICATIONS = False

class ProductionConfig(Config):
    """Configuración para producción"""
    DEBUG = False
    
    # Seguridad en producción
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # Configuración de respaldos más estricta
    VERIFY_CHECKSUM = True
    VERIFY_FILE_SIZE = True
    SEND_BACKUP_NOTIFICATIONS = True

class TestingConfig(Config):
    """Configuración para testing"""
    TESTING = True
    DEBUG = True
    
    # Para testing, usar una base de datos diferente
    MONGO_URI = os.environ.get('TEST_MONGO_URI') or 'mongodb://localhost:27017/test_gestion_plantas'
    BACKUP_DIR = os.path.join(basedir, 'test_backups')

# Diccionario de configuraciones
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}