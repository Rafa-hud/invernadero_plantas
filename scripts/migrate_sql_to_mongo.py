import mysql.connector
import os
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import timedelta # Asegúrate de tener este import arriba

load_dotenv()

def obtener_conexion_sql():
    # En MySQL no pasamos una ruta de archivo, sino credenciales de acceso
    try:
        conn = mysql.connector.connect(
            host="localhost",          # O la IP de tu servidor
            user="root",               # Tu usuario de SQLyog
            password="",    # Tu contraseña
            database="gestion_plantas" # El nombre de la base de datos en SQLyog
        )
        return conn
    except mysql.connector.Error as err:
        print(f"❌ Error de conexión MySQL: {err}")
        raise

def obtener_conexion_mongo():
    uri = os.getenv("MONGO_URI")
    client = MongoClient(uri)
    return client.invernadero_db

def migrar_usuarios(cursor_sql, db_mongo):
    print("Migrando usuarios...")
    cursor_sql.execute("SELECT * FROM usuarios")
    
    # IMPORTANTE: En mysql-connector, usamos dictionary=True en el cursor
    # por lo que 'row' ya es un diccionario.
    usuarios = cursor_sql.fetchall()
    
    if usuarios:
        db_mongo.users.insert_many(usuarios)
        print(f"✅ {len(usuarios)} usuarios migrados.")

def migrar_pedidos_con_detalles(cursor_sql, db_mongo):
    print("Migrando pedidos y embebiendo detalles...")
    cursor_sql.execute("SELECT * FROM pedidos")
    pedidos_sql = cursor_sql.fetchall()
    
    pedidos_mongo = []
    
    for pedido_dict in pedidos_sql:
        id_pedido_sql = pedido_dict['id_pedido']
        
        # MySQL usa '%s' como placeholder, a diferencia del '?' de SQLite
        query_detalles = "SELECT * FROM pedido_detalle WHERE id_pedido = %s"
        cursor_sql.execute(query_detalles, (id_pedido_sql,))
        detalles_sql = cursor_sql.fetchall()
        
        pedido_dict['detalles'] = detalles_sql
        pedidos_mongo.append(pedido_dict)
        
    if pedidos_mongo:
        db_mongo.orders.insert_many(pedidos_mongo)
        print(f"✅ {len(pedidos_mongo)} pedidos migrados.")

def migrar_programaciones(cursor_sql, db_mongo):
    print("Migrando programaciones de respaldo...")
    # Ejecutamos la consulta
    cursor_sql.execute("SELECT * FROM programaciones_respaldos") 
    
    # Al usar cursor(dictionary=True), fetchall() ya devuelve una lista de diccionarios
    programaciones = cursor_sql.fetchall()
    
    if programaciones:
        db_mongo.schedules.insert_many(programaciones)
        print(f"✅ {len(programaciones)} programaciones migradas a la colección 'schedules'.")
    else:
        print("⚠️ No hay datos en la tabla 'programaciones'.")

def migrar_respaldos(cursor_sql, db_mongo):
    print("Migrando historial de respaldos...")
    cursor_sql.execute("SELECT * FROM respaldos")
    
    respaldos = cursor_sql.fetchall()
    
    if respaldos:
        db_mongo.backups.insert_many(respaldos)
        print(f"✅ {len(respaldos)} registros de respaldo migrados a la colección 'backups'.")
    else:
        print("⚠️ No hay datos en la tabla 'respaldos'.")

def migrar_plantas(cursor_sql, db_mongo):
    print("Migrando plantas...")
    # 1. Ejecutamos la consulta en MySQL
    cursor_sql.execute("SELECT * FROM plantas")
    
    # 2. Obtenemos todas las filas como una lista de diccionarios
    plantas = cursor_sql.fetchall()
    
    if plantas:
        # 3. Insertamos en la colección 'plants' de MongoDB Atlas
        db_mongo.plants.insert_many(plantas)
        print(f"✅ {len(plantas)} plantas migradas exitosamente.")
    else:
        print("⚠️ No se encontraron plantas en MySQL para migrar.")

def main():
    print("Iniciando migración de MySQL a MongoDB Atlas...")
    try:
        conn_sql = obtener_conexion_sql()
        
        # CLAVE: dictionary=True hace que fetchall() devuelva una lista de diccionarios
        # Esto reemplaza al row_factory de SQLite.
        cursor_sql = conn_sql.cursor(dictionary=True) 
        
        db_mongo = obtener_conexion_mongo()
        
        # Limpieza (Opcional)
        db_mongo.users.drop()
        db_mongo.orders.drop()
        db_mongo.schedules.drop() # Limpiar nuevas colecciones
        db_mongo.backups.drop()
        db_mongo.plants.drop()
        
        # Ejecutar
        migrar_usuarios(cursor_sql, db_mongo)
        migrar_plantas(cursor_sql, db_mongo) # Asegúrate de definirla igual
        migrar_pedidos_con_detalles(cursor_sql, db_mongo)
        migrar_programaciones(cursor_sql, db_mongo)
        migrar_respaldos(cursor_sql, db_mongo)
        
        print("🚀 Migración desde MySQL completada con éxito.")
        
    except Exception as e:
        print(f"❌ Error durante la migración: {e}")
    finally:
        if 'conn_sql' in locals() and conn_sql.is_connected():
            cursor_sql.close()
            conn_sql.close()

if __name__ == "__main__":
    main()