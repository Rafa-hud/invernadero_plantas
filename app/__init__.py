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
    config[config_name].init_app(app)
    
    # Agregar variable global 'now' a todas las plantillas
    @app.context_processor
    def inject_now():
        from datetime import datetime
        return {'now': datetime.utcnow()}
    
    # Inicializar extensiones
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    
    # Configurar logging
    if not app.debug:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/plantas.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Sistema de Gestión de Plantas iniciado')
    
    # Registrar blueprints (rutas) - EXCLUIR TIENDA POR AHORA
    from app.routes import auth_bp, main_bp, plants_bp, backup_bp, reports_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(plants_bp, url_prefix='/plantas')
    app.register_blueprint(backup_bp, url_prefix='/respaldos')
    app.register_blueprint(reports_bp, url_prefix='/reportes')
    
    # ========== REGISTRAR TIENDA SOLO SI NO TIENE ERRORES ==========
    try:
        # Primero verificar si el blueprint existe
        from app.routes import tienda_bp
        
        # Verificar que no haya endpoints duplicados
        import inspect
        endpoints = {}
        duplicate_endpoints = []
        
        # Obtener todas las funciones del blueprint
        for name, func in inspect.getmembers(tienda_bp):
            if hasattr(func, '__name__'):
                endpoint_name = f"tienda.{func.__name__}"
                if endpoint_name in endpoints:
                    duplicate_endpoints.append(endpoint_name)
                else:
                    endpoints[endpoint_name] = func
        
        if duplicate_endpoints:
            app.logger.warning(f'Endpoints duplicados en tienda_bp: {duplicate_endpoints}')
            app.logger.warning('Blueprint de tienda NO registrado debido a endpoints duplicados')
        else:
            app.register_blueprint(tienda_bp, url_prefix='/tienda')
            app.logger.info('Blueprint de tienda registrado exitosamente')
            
    except ImportError:
        app.logger.warning('Blueprint de tienda no encontrado en routes.py')
    except Exception as e:
        app.logger.error(f'Error al registrar blueprint de tienda: {str(e)}')
    
    # Crear tablas si no existen
    with app.app_context():
        try:
            db.create_all()
            app.logger.info('Tablas de base de datos verificadas/creadas')
        except Exception as e:
            app.logger.error(f'Error al crear tablas: {str(e)}')
        
        # Crear usuario admin por defecto si no existe
        try:
            from app.models import Usuario
            from werkzeug.security import generate_password_hash
            
            admin = Usuario.query.filter_by(correo='admin@plantas.com').first()
            if not admin:
                admin = Usuario(
                    nombre='Administrador',
                    correo='admin@plantas.com',
                    rol='admin'
                )
                admin.contrasenia_hash = generate_password_hash('Admin123!')
                db.session.add(admin)
                db.session.commit()
                app.logger.info('Usuario administrador creado por defecto')
                
            # Crear usuario cliente de prueba si no existe
            cliente = Usuario.query.filter_by(correo='cliente@ejemplo.com').first()
            if not cliente:
                cliente = Usuario(
                    nombre='Cliente Demo',
                    correo='cliente@ejemplo.com',
                    rol='cliente'
                )
                cliente.contrasenia_hash = generate_password_hash('Cliente123!')
                db.session.add(cliente)
                db.session.commit()
                app.logger.info('Usuario cliente demo creado por defecto')
                
        except Exception as e:
            app.logger.error(f'Error al crear usuarios por defecto: {str(e)}')
    
    return app