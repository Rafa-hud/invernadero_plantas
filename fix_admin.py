# fix_admin.py
import os
import sys
from sqlalchemy import create_engine, text
from werkzeug.security import generate_password_hash

# Configuración
DATABASE_URL = 'mysql+mysqlconnector://root:@localhost:3306/gestion_plantas'

print("🛠️  Corrigiendo usuario administrador...")

try:
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # 1. Eliminar el usuario admin existente (si existe)
        conn.execute(text("DELETE FROM usuarios WHERE correo = 'admin@plantas.com'"))
        conn.commit()
        print("✅ Usuario admin antiguo eliminado")
        
        # 2. Generar hash correcto para la contraseña
        password = 'Admin123!'
        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        
        print(f"🔐 Contraseña: {password}")
        print(f"🔑 Hash generado: {password_hash[:50]}...")
        
        # 3. Insertar usuario admin con hash correcto
        sql = text("""
            INSERT INTO usuarios (nombre, correo, contrasenia_hash, rol, activo) 
            VALUES (:nombre, :correo, :hash, :rol, :activo)
        """)
        
        conn.execute(sql, {
            'nombre': 'Administrador',
            'correo': 'admin@plantas.com',
            'hash': password_hash,
            'rol': 'admin',
            'activo': 1
        })
        conn.commit()
        
        print("✅ Usuario admin creado correctamente")
        print(f"📧 Correo: admin@plantas.com")
        print(f"🔐 Contraseña: Admin123!")
        print(f"👑 Rol: admin")
        
        # 4. Verificar que se insertó correctamente
        result = conn.execute(text("SELECT nombre, correo FROM usuarios WHERE correo = 'admin@plantas.com'"))
        user = result.fetchone()
        
        if user:
            print(f"\n🎉 Usuario verificado: {user[0]} ({user[1]})")
        else:
            print("❌ Error: Usuario no encontrado después de insertar")
            
except Exception as e:
    print(f"❌ Error: {e}")