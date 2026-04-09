# run.py
import os
import sys
from dotenv import load_dotenv

# 1. Cargar las variables del .env
load_dotenv()

# --- CONFIGURACIÓN DE RUTAS ---
# Obtenemos la ruta absoluta de la carpeta raíz (Invernadero_plantas-)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Insertamos la raíz al inicio de sys.path para que 'app' y 'config' sean visibles
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Sincronizamos la variable de entorno para los subprocesos de Spark/Streamlit
os.environ["PYTHONPATH"] = BASE_DIR

# 2. IMPORTACIÓN DE LA APP (Debe ir después de configurar sys.path)
try:
    from app import create_app
except ImportError as e:
    print(f"❌ Error de importación: {e}")
    print("Tip: Asegúrate de que no exista un archivo '__init__.py' en la raíz o en 'config' que cause colisiones.")
    sys.exit(1)

app = create_app('development')

if __name__ == '__main__':
    print("=" * 60)
    print("🌿 INTELLIGENCE PLANT - SERVIDOR DE GESTIÓN")
    print("=" * 60)
    
    try:
        print("🌐 Iniciando Servidor Vivero Digital (Flask)...")
        print(f"🔗 URL Local: http://localhost:5000")
        print("=" * 60)
        print("Los algoritmos de Spark se ejecutarán desde la interfaz web.")
        print("Presiona Ctrl+C para detener el servidor.\n")
        
        # Ejecutamos Flask
        # Nota: use_reloader=False evita que el servidor se reinicie dos veces
        # lo cual es más estable cuando lanzas subprocesos de Spark.
        app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)

    except KeyboardInterrupt:
        print("\n🛑 Apagando servidor...")
        print("✅ Sistema cerrado correctamente.")