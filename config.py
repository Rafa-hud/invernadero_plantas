# config.py
import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Configuración básica
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave-secreta-muy-segura-plantas-2026'
    
    # Base de datos MySQL para XAMPP
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'mysql+mysqlconnector://root:@localhost/gestion_plantas?charset=utf8mb4'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': 280,
        'pool_pre_ping': True
    }
    
    # Configuración de sesión
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=60)
    SESSION_COOKIE_SECURE = False  # Cambia a True en producción con HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # ========== CONFIGURACIÓN PARA RESPALDOS ==========
    # Credenciales de MySQL para mysqldump
    MYSQL_HOST = 'localhost'
    MYSQL_PORT = 3306
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = ''
    MYSQL_DATABASE = 'gestion_plantas'
    
    # Configuración de backup
    BACKUP_DIR = os.path.join(basedir, 'backups')
    BACKUP_RETENTION_DAYS = 30
    
    # Tipos de backup soportados
    BACKUP_TYPES = ['completo', 'diferencial', 'minima_modificacion']
    
    # Rutas de comandos MySQL - usar rutas relativas para evitar errores
    # En desarrollo, usar comandos del PATH
    MYSQLDUMP_PATH = None  # Se establecerá dinámicamente
    MYSQL_PATH = None      # Se establecerá dinámicamente
    
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
    STORAGE_MEDIA = ['local']
    
    # Configuración de correo
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    
    # Configuración de migraciones
    SQLALCHEMY_DATABASE_URI_MIGRATIONS = None
    
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
        
        # Verificar comandos MySQL
        Config._verificar_comandos_mysql()
        
        # Verificar configuración MySQL
        print(f"📋 Configuración MySQL:")
        print(f"   Host: {Config.MYSQL_HOST}")
        print(f"   Usuario: {Config.MYSQL_USER}")
        print(f"   Base de datos: {Config.MYSQL_DATABASE}")
        print(f"   Puerto: {Config.MYSQL_PORT}")
        print(f"   Carpeta respaldos: {Config.BACKUP_DIR}")
    
    @staticmethod
    def _verificar_comandos_mysql():
        """Verificar y configurar comandos MySQL dinámicamente"""
        import subprocess
        import sys
        
        # Rutas comunes para XAMPP en Windows
        rutas_mysql_windows = [
            r'C:\xampp\mysql\bin\mysqldump.exe',
            r'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe',
            r'C:\Program Files\MySQL\MySQL Server 5.7\bin\mysqldump.exe'
        ]
        
        # Buscar mysqldump
        mysqldump_encontrado = False
        mysql_encontrado = False
        
        # Primero intentar con el PATH del sistema
        try:
            result = subprocess.run(['mysqldump', '--version'], 
                                  capture_output=True, text=True, shell=True)
            if result.returncode == 0:
                Config.MYSQLDUMP_PATH = 'mysqldump'
                Config.MYSQL_PATH = 'mysql'
                mysqldump_encontrado = True
                mysql_encontrado = True
                print("✅ mysqldump encontrado en PATH del sistema")
        except:
            pass
        
        # Si no está en PATH, buscar en rutas específicas (Windows)
        if not mysqldump_encontrado and sys.platform == 'win32':
            for ruta in rutas_mysql_windows:
                if os.path.exists(ruta):
                    Config.MYSQLDUMP_PATH = ruta
                    Config.MYSQL_PATH = ruta.replace('mysqldump.exe', 'mysql.exe')
                    mysqldump_encontrado = True
                    if os.path.exists(Config.MYSQL_PATH):
                        mysql_encontrado = True
                    print(f"✅ MySQL encontrado en: {ruta}")
                    break
        
        if not mysqldump_encontrado:
            print("⚠️  mysqldump no encontrado. Los respaldos pueden fallar.")
        if not mysql_encontrado:
            print("⚠️  mysql no encontrado. La restauración puede fallar.")

class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True
    SQLALCHEMY_ECHO = True
    
    # Para desarrollo, desactivamos algunas verificaciones estrictas
    VERIFY_CHECKSUM = False
    SEND_BACKUP_NOTIFICATIONS = False

class ProductionConfig(Config):
    """Configuración para producción"""
    DEBUG = False
    SQLALCHEMY_ECHO = False
    
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
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    
    # Para testing, usar SQLite
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'test_user'
    MYSQL_PASSWORD = 'test_pass'
    MYSQL_DATABASE = 'test_db'
    BACKUP_DIR = os.path.join(basedir, 'test_backups')

# Diccionario de configuraciones
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

def get_mysql_config():
    """Obtener configuración MySQL para respaldos"""
    import sys
    from flask import current_app
    
    # Si estamos fuera del contexto de la app
    if 'current_app' not in locals() or not current_app:
        return {
            'host': Config.MYSQL_HOST,
            'port': Config.MYSQL_PORT,
            'user': Config.MYSQL_USER,
            'password': Config.MYSQL_PASSWORD,
            'database': Config.MYSQL_DATABASE,
            'mysqldump_path': Config.MYSQLDUMP_PATH,
            'mysql_path': Config.MYSQL_PATH
        }
    
    # Dentro del contexto de la app
    try:
        return {
            'host': current_app.config.get('MYSQL_HOST', Config.MYSQL_HOST),
            'port': current_app.config.get('MYSQL_PORT', Config.MYSQL_PORT),
            'user': current_app.config.get('MYSQL_USER', Config.MYSQL_USER),
            'password': current_app.config.get('MYSQL_PASSWORD', Config.MYSQL_PASSWORD),
            'database': current_app.config.get('MYSQL_DATABASE', Config.MYSQL_DATABASE),
            'mysqldump_path': current_app.config.get('MYSQLDUMP_PATH', Config.MYSQLDUMP_PATH),
            'mysql_path': current_app.config.get('MYSQL_PATH', Config.MYSQL_PATH)
        }
    except:
        return {
            'host': Config.MYSQL_HOST,
            'port': Config.MYSQL_PORT,
            'user': Config.MYSQL_USER,
            'password': Config.MYSQL_PASSWORD,
            'database': Config.MYSQL_DATABASE,
            'mysqldump_path': Config.MYSQLDUMP_PATH,
            'mysql_path': Config.MYSQL_PATH
        }