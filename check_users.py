# check_users.py
import os
import sys
from sqlalchemy import create_engine, text

# Configuración
DATABASE_URL = 'mysql+mysqlconnector://root:@localhost:3306/gestion_plantas'

print("🔍 Verificando usuarios en la base de datos...")

try:
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Verificar todos los usuarios
        result = conn.execute(text("SELECT id, nombre, correo, contrasenia_hash, rol FROM usuarios"))
        users = result.fetchall()
        
        print(f"👤 Usuarios encontrados: {len(users)}")
        print("=" * 80)
        
        for user in users:
            print(f"ID: {user[0]}")
            print(f"Nombre: {user[1]}")
            print(f"Correo: {user[2]}")
            print(f"Hash: {user[3][:50]}..." if user[3] and len(user[3]) > 50 else f"Hash: {user[3]}")
            print(f"Rol: {user[3]}")
            print("-" * 40)
            
except Exception as e:
    print(f"❌ Error: {e}")