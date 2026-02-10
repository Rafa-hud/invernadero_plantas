from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import config
import logging
from logging.handlers import RotatingFileHandler
import os
from flask_mail import Mail

# Inicializar extensiones
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
mail = Mail()

# Configurar login manager
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Por favor inicia sesión para acceder a esta página.'
login_manager.login_message_category = 'warning'

def create_app(config_name='default'):
    """Factory function para crear la aplicación Flask"""
    
    app = Flask(__name__)
    
    # Cargar configuración
    app.config.from_object(config[config_name])
    
    # Inicializar configuración si existe el método init_app
    if hasattr(config[config_name], 'init_app'):
        config[config_name].init_app(app)
    
    # ========== CONFIGURACIÓN PARA IMÁGENES ==========
    # Tamaño máximo para uploads de imágenes (10MB)
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
    
    # Extensiones permitidas para imágenes
    app.config['ALLOWED_IMAGE_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
    
    # Carpeta para uploads
    app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'uploads')
    app.config['PLANTAS_UPLOAD_FOLDER'] = os.path.join(app.config['UPLOAD_FOLDER'], 'plantas')
    app.config['USERS_UPLOAD_FOLDER'] = os.path.join(app.config['UPLOAD_FOLDER'], 'usuarios')
    # ==============================================
    
    # Agregar variable global 'now' a todas las plantillas
    @app.context_processor
    def inject_datetime():
        from datetime import datetime
        return {'datetime': datetime, 'now': datetime.now()}
    
    # Inyectar configuración de la app en templates
    @app.context_processor
    def inject_config():
        return {
            'app_name': app.config.get('APP_NAME', 'Gestión de Plantas'),
            'debug': app.debug,
            'config': app.config
        }
        
    # Inicializar extensiones con la aplicación
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    
    # Configurar logging
    configure_logging(app)
    
    # Registrar blueprints (rutas)
    register_blueprints(app)
    
    # Configurar y verificar carpetas necesarias
    setup_folders(app)
    
    # Inicializar base de datos y datos por defecto
    setup_database(app)
    
    # Configurar planificador de respaldos
    setup_backup_scheduler(app)
    
    return app

def configure_logging(app):
    """Configurar sistema de logging"""
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        # Handler para archivo
        file_handler = RotatingFileHandler(
            'logs/plantas.log', 
            maxBytes=10485760,  # 10MB
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s '
            '[in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        
        # Configurar logger de la aplicación
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Sistema de Gestión de Plantas iniciado')
        
        # Configurar logger de SQLAlchemy
        logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    else:
        # En modo debug, usar consola
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(logging.Formatter(
            '%(name)-12s: %(levelname)-8s %(message)s'
        ))
        app.logger.addHandler(console_handler)
        app.logger.setLevel(logging.DEBUG)

def register_blueprints(app):
    """Registrar todos los blueprints de la aplicación"""
    
    # Importar blueprints
    try:
        from app.routes import auth_bp, main_bp, plants_bp, backup_bp, reports_bp
        
        # Registrar blueprints principales
        app.register_blueprint(auth_bp, url_prefix='/auth')
        app.register_blueprint(main_bp)
        app.register_blueprint(plants_bp, url_prefix='/plantas')
        app.register_blueprint(backup_bp, url_prefix='/respaldos')
        app.register_blueprint(reports_bp, url_prefix='/reportes')
        
        app.logger.info('Blueprints principales registrados exitosamente')
        
    except ImportError as e:
        app.logger.error(f'Error importando blueprints principales: {e}')
        raise
    
    # ========== REGISTRAR TIENDA ==========
    try:
        from app.routes import tienda_bp
        app.register_blueprint(tienda_bp, url_prefix='/tienda')
        app.logger.info('Blueprint de tienda registrado exitosamente')
            
    except ImportError as e:
        app.logger.warning(f'Blueprint de tienda no encontrado: {e}')
    except Exception as e:
        app.logger.error(f'Error al registrar blueprint de tienda: {str(e)}')

def setup_folders(app):
    """Crear y verificar carpetas necesarias"""
    
    carpetas_necesarias = [
        'backups',
        'logs',
        app.config['UPLOAD_FOLDER'],
        app.config['PLANTAS_UPLOAD_FOLDER'],
        app.config['USERS_UPLOAD_FOLDER']
    ]
    
    for carpeta in carpetas_necesarias:
        try:
            if not os.path.exists(carpeta):
                os.makedirs(carpeta, exist_ok=True)
                app.logger.info(f'Carpeta creada: {carpeta}')
        except Exception as e:
            app.logger.error(f'Error creando carpeta {carpeta}: {str(e)}')

def setup_database(app):
    """Configurar base de datos y crear datos por defecto"""
    
    with app.app_context():
        try:
            # Crear tablas si no existen
            db.create_all()
            app.logger.info('Tablas de base de datos verificadas/creadas')
            
            # Crear datos por defecto
            create_default_data(app)
            
        except Exception as e:
            app.logger.error(f'Error al configurar base de datos: {str(e)}')

def create_default_data(app):
    """Crear datos por defecto en la base de datos"""
    
    from app.models import Usuario
    from werkzeug.security import generate_password_hash
    
    try:
        # Crear usuario admin por defecto si no existe
        admin_email = app.config.get('DEFAULT_ADMIN_EMAIL', 'admin@plantas.com')
        admin_password = app.config.get('DEFAULT_ADMIN_PASSWORD', 'Admin123!')
        
        admin = Usuario.query.filter_by(correo=admin_email).first()
        if not admin:
            admin = Usuario(
                nombre='Administrador',
                correo=admin_email,
                rol='admin',
                estado='activo'
            )
            admin.contrasenia_hash = generate_password_hash(admin_password)
            db.session.add(admin)
            app.logger.info('Usuario administrador creado por defecto')
        
        # Crear usuario cliente de prueba si no existe
        cliente_email = app.config.get('DEFAULT_CLIENT_EMAIL', 'cliente@ejemplo.com')
        cliente_password = app.config.get('DEFAULT_CLIENT_PASSWORD', 'Cliente123!')
        
        cliente = Usuario.query.filter_by(correo=cliente_email).first()
        if not cliente:
            cliente = Usuario(
                nombre='Cliente Demo',
                correo=cliente_email,
                rol='cliente',
                estado='activo'
            )
            cliente.contrasenia_hash = generate_password_hash(cliente_password)
            db.session.add(cliente)
            app.logger.info('Usuario cliente demo creado por defecto')
        
        # Commit de todos los cambios
        db.session.commit()
            
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error al crear datos por defecto: {str(e)}')

def setup_backup_scheduler(app):
    """Configurar planificador de respaldos automáticos"""
    
    try:
        from app.scheduler import backup_scheduler
        
        # Iniciar el planificador solo si no está en modo testing
        if not app.testing:
            backup_scheduler.start(app)
            app.logger.info('Planificador de respaldos automáticos iniciado')
        else:
            app.logger.info('Modo testing - Planificador de respaldos desactivado')
            
    except ImportError as e:
        app.logger.warning(f'No se pudo cargar el planificador de respaldos: {e}')
        app.logger.warning('La funcionalidad de respaldos programados no estará disponible')
    except Exception as e:
        app.logger.error(f'Error al iniciar el planificador de respaldos: {str(e)}')
        app.logger.error('La funcionalidad de respaldos programados no estará disponible')
    
    # Configurar cierre del planificador
    @app.teardown_appcontext
    def shutdown_scheduler(exception=None):
        """Detener el planificador cuando la aplicación se cierra"""
        try:
            from app.scheduler import backup_scheduler
            if hasattr(backup_scheduler, 'running') and backup_scheduler.running:
                backup_scheduler.stop()
                app.logger.info('Planificador de respaldos detenido')
        except Exception as e:
            app.logger.error(f'Error deteniendo planificador: {str(e)}')