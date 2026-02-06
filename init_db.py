import os
import sys
from app import create_app, db
from app.models import Usuario

# Crear directorio de base de datos si no existe
if not os.path.exists('database'):
    os.makedirs('database')

app = create_app()

with app.app_context():
    # Crear todas las tablas
    db.create_all()
    
    # Crear usuario admin si no existe
    admin = Usuario.query.filter_by(correo='admin@plantas.com').first()
    if not admin:
        admin = Usuario(
            nombre='Administrador',
            correo='admin@plantas.com',
            rol='admin'
        )
        admin.contrasenia = 'Admin123!'
        db.session.add(admin)
        db.session.commit()
        print("✅ Base de datos creada con usuario admin")
    
    print("✅ Base de datos SQLite lista en: database/gestion_plantas.db")