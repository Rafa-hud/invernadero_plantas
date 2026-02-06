import os
import sys
from sqlalchemy import create_engine, text

# Configuración de conexión
DATABASE_URL = 'mysql+mysqlconnector://root:@localhost:3306/gestion_plantas'

print("🔍 Probando conexión a MySQL XAMPP...")
print(f"URL: {DATABASE_URL}")

try:
    # Crear conexión
    engine = create_engine(DATABASE_URL)
    
    # Probar conexión
    with engine.connect() as conn:
        # Verificar base de datos
        result = conn.execute(text("SELECT DATABASE()"))
        db_name = result.fetchone()[0]
        print(f"✅ Conectado a base de datos: {db_name}")
        
        # Verificar tablas
        result = conn.execute(text("SHOW TABLES"))
        tables = [row[0] for row in result.fetchall()]
        
        print(f"📊 Tablas encontradas ({len(tables)}):")
        for table in tables:
            print(f"  - {table}")
        
        # Verificar usuario admin
        result = conn.execute(text("SELECT nombre, correo, rol FROM usuarios WHERE rol = 'admin'"))
        admins = result.fetchall()
        
        print(f"👤 Usuarios administradores:")
        for admin in admins:
            print(f"  - {admin[0]} ({admin[1]}) - Rol: {admin[2]}")
        
        # Contar registros
        tables_to_check = ['usuarios', 'plantas', 'registros_riego']
        for table in tables_to_check:
            if table in tables:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.fetchone()[0]
                print(f"  {table}: {count} registros")
    
    print("\n🎉 ¡Conexión exitosa! Todo está listo.")
    
except Exception as e:
    print(f"\n❌ Error de conexión: {e}")
    print("\n🔧 Solución de problemas:")
    print("1. Verifica que XAMPP esté ejecutándose")
    print("2. Asegúrate que MySQL esté iniciado en XAMPP")
    print("3. Verifica que la base de datos 'gestion_plantas' exista")
    print("4. Prueba conectarte con:")
    print("   - Usuario: root")
    print("   - Contraseña: (vacía)")
    print("   - Host: localhost")
    print("   - Puerto: 3306")
    
    input("\nPresiona Enter para salir...")