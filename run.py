# run.py
import os
import sys
import subprocess
from dotenv import load_dotenv

# 1. Cargar las variables del .env
load_dotenv()

# --- CONFIGURACIÓN DE RUTAS ---
# Obtenemos la ruta absoluta de la carpeta raíz (donde está este run.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Aseguramos que la raíz esté en el path
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Sincronizamos PYTHONPATH para que los scripts en spark/ encuentren a app.config
os.environ["PYTHONPATH"] = BASE_DIR

# 2. IMPORTACIÓN DE LA APP
try:
    # Como moviste 'config' dentro de 'app', ya no habrá colisión con archivos de la raíz
    from app import create_app
except ImportError as e:
    print(f"❌ Error de importación: {e}")
    print("Verifica que la carpeta 'app' contenga un archivo '__init__.py'.")
    sys.exit(1)

app = create_app('development')

def limpiar_puertos_streamlit():
    """Limpia procesos de Streamlit que hayan quedado colgados en el puerto 8501."""
    try:
        # Comando para Linux para liberar el puerto 8501 y evitar errores de puerto ocupado
        subprocess.run(["fuser", "-k", "8501/tcp"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        print("🧹 Puerto 8501 liberado correctamente.")
    except Exception:
        # En caso de no tener privilegios o no estar en Linux, ignoramos el error
        pass

if __name__ == '__main__':
    print("=" * 60)
    print("🌿 INTELLIGENCE PLANT - SISTEMA DE ANALÍTICA")
    print("=" * 60)
    
    # Limpieza preventiva de puertos
    limpiar_puertos_streamlit()
    
    try:
        print("🌐 Panel de Control: http://localhost:5000")
        print("📊 Dashboards Spark: http://localhost:8501")
        print("=" * 60)
        
        # --- CONFIGURACIÓN DE EJECUCIÓN ---
        # debug=True: Útil para ver errores en desarrollo.
        # use_reloader=False: CLAVE para evitar que Flask se reinicie y abra pestañas dobles.
        app.run(
            debug=True, 
            host='0.0.0.0', 
            port=5000, 
            use_reloader=False 
        )

    except KeyboardInterrupt:
        print("\n🛑 Apagando servicios...")
        limpiar_puertos_streamlit()
        print("✅ Servidor detenido y recursos liberados.")