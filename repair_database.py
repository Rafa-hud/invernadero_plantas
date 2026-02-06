#!/usr/bin/env python3
"""
Script para reparar completamente la base de datos del Sistema de Plantas
"""

import os
import sys
from sqlalchemy import create_engine, text
from werkzeug.security import generate_password_hash

def print_header(title):
    print("\n" + "=" * 60)
    print(f"🛠️  {title}")
    print("=" * 60)

def main():
    print("🔧 REPARADOR DE BASE DE DATOS - SISTEMA DE PLANTAS 🔧")
    
    # Configuración
    DATABASE_URL = 'mysql+mysqlconnector://root:@localhost:3306/gestion_plantas'
    
    try:
        engine = create_engine(DATABASE_URL)
        
        with engine.connect() as conn:
            print_header("1. VERIFICANDO CONEXIÓN")
            conn.execute(text("SELECT 1"))
            print("✅ Conectado a MySQL correctamente")
            
            print_header("2. VERIFICANDO TABLAS")
            result = conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result.fetchall()]
            
            required_tables = ['usuarios', 'plantas', 'registros_riego', 'respaldos', 'historial_accesos']
            missing_tables = [t for t in required_tables if t not in tables]
            
            if missing_tables:
                print(f"❌ Tablas faltantes: {missing_tables}")
                print("⚠️  Ejecuta el SQL en phpMyAdmin para crear las tablas")
                return
            else:
                print("✅ Todas las tablas existen")
            
            print_header("3. REPARANDO USUARIO ADMIN")
            
            # Verificar usuario admin actual
            result = conn.execute(text("""
                SELECT id, nombre, correo, LENGTH(contrasenia_hash) as hash_len 
                FROM usuarios WHERE correo = 'admin@plantas.com'
            """))
            admin = result.fetchone()
            
            if admin:
                print(f"⚠️  Usuario admin encontrado:")
                print(f"   ID: {admin[0]}")
                print(f"   Nombre: {admin[1]}")
                print(f"   Longitud hash: {admin[3]}")
                
                # Preguntar si reemplazar
                respuesta = input("\n¿Reemplazar usuario admin? (s/n): ").lower()
                if respuesta == 's':
                    conn.execute(text("DELETE FROM usuarios WHERE correo = 'admin@plantas.com'"))
                    conn.commit()
                    print("✅ Usuario admin eliminado")
                else:
                    print("⚠️  Manteniendo usuario actual")
                    return
            
            # Crear nuevo usuario admin con hash correcto
            password = 'Admin123!'
            password_hash = generate_password_hash(password, method='pbkdf2:sha256')
            
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
            
            print("✅ Nuevo usuario admin creado")
            print(f"   📧 Correo: admin@plantas.com")
            print(f"   🔐 Contraseña: {password}")
            print(f"   🔑 Hash: {password_hash[:50]}...")
            
            print_header("4. VERIFICANDO DATOS DE EJEMPLO")
            
            # Verificar plantas de ejemplo
            result = conn.execute(text("SELECT COUNT(*) FROM plantas"))
            plant_count = result.fetchone()[0]
            
            if plant_count == 0:
                print("⚠️  No hay plantas de ejemplo")
                print("   Creando plantas de ejemplo...")
                
                # Obtener ID del usuario admin
                result = conn.execute(text("SELECT id FROM usuarios WHERE correo = 'admin@plantas.com'"))
                admin_id = result.fetchone()[0]
                
                # Insertar plantas de ejemplo
                plantas = [
                    ('Monstera Deliciosa', 'Monstera deliciosa', admin_id),
                    ('Suculenta Echeveria', 'Echeveria elegans', admin_id),
                    ('Lavanda', 'Lavandula angustifolia', admin_id)
                ]
                
                for nombre, especie, usuario_id in plantas:
                    conn.execute(text("""
                        INSERT INTO plantas (nombre, especie, usuario_id, estado)
                        VALUES (:nombre, :especie, :usuario_id, 'activa')
                    """), {'nombre': nombre, 'especie': especie, 'usuario_id': usuario_id})
                
                conn.commit()
                print("✅ 3 plantas de ejemplo creadas")
            else:
                print(f"✅ {plant_count} plantas encontradas en el sistema")
            
            print_header("5. RESUMEN FINAL")
            
            # Contar registros
            for table in required_tables:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.fetchone()[0]
                print(f"   📊 {table}: {count} registros")
            
            # Verificar usuario admin
            result = conn.execute(text("""
                SELECT u.nombre, u.correo, u.rol, 
                       (SELECT COUNT(*) FROM plantas p WHERE p.usuario_id = u.id) as plantas_count
                FROM usuarios u 
                WHERE u.correo = 'admin@plantas.com'
            """))
            admin_info = result.fetchone()
            
            if admin_info:
                print(f"\n👤 USUARIO ADMIN:")
                print(f"   Nombre: {admin_info[0]}")
                print(f"   Correo: {admin_info[1]}")
                print(f"   Rol: {admin_info[2]}")
                print(f"   Plantas: {admin_info[3]}")
            
            print("\n" + "=" * 60)
            print("🎉 ¡BASE DE DATOS REPARADA EXITOSAMENTE! 🎉")
            print("=" * 60)
            print("\n📋 INSTRUCCIONES:")
            print("1. Ejecuta el sistema: python run.py")
            print("2. Accede a: http://localhost:5000/auth/login")
            print("3. Usa: admin@plantas.com / Admin123!")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\n🔧 SOLUCIÓN DE PROBLEMAS:")
        print("1. Asegúrate que XAMPP esté ejecutándose")
        print("2. Verifica que MySQL esté iniciado")
        print("3. Abre http://localhost/phpmyadmin")
        print("4. Verifica que la base de datos 'gestion_plantas' exista")
        
        input("\nPresiona Enter para salir...")
        sys.exit(1)

if __name__ == '__main__':
    main()