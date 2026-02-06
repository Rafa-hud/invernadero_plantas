# __init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import config
import logging
from logging.handlers import RotatingFileHandler
import os

# Inicializar extensiones
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

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
    
    # Registrar blueprints (rutas)
    from app.routes import auth_bp, main_bp, plants_bp, backup_bp, reports_bp, tienda_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(plants_bp, url_prefix='/plantas')
    app.register_blueprint(backup_bp, url_prefix='/respaldos')
    app.register_blueprint(reports_bp, url_prefix='/reportes')
    app.register_blueprint(tienda_bp, url_prefix='/tienda')
    
    # Crear tablas si no existen
    with app.app_context():
        db.create_all()
        
        # Crear usuario admin por defecto si no existe
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
    
    return app