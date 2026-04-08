# run.py
import os
import sys
import subprocess
import time
from multiprocessing import Process
from dotenv import load_dotenv

# 1. Cargar las variables del .env
load_dotenv()

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app import create_app
except ImportError as e:
    print(f"❌ Error de importación: {e}")
    sys.exit(1)

app = create_app('development')

# --- FUNCIÓN PARA EJECUTAR EL DASHBOARD DE SPARK ---
def ejecutar_streamlit():
    """Lanza el dashboard de Streamlit que está en la carpeta spark."""
    print("🚀 Iniciando Dashboard de Analítica (Spark/Streamlit)...")
    # Ruta al archivo dentro de la carpeta spark
    ruta_spark = os.path.join("spark", "regresion_analytics_graficos_dash.py")
    
    try:
        # Ejecuta: streamlit run spark/regresion_analytics_graficos_dash.py
        subprocess.check_call(["streamlit", "run", ruta_spark])
    except Exception as e:
        print(f"❌ Error al iniciar Streamlit: {e}")

# --- FUNCIÓN PARA EJECUTAR FLASK ---
def ejecutar_flask():
    """Lanza la aplicación principal de Flask."""
    print("🌐 Iniciando Servidor Principal (Flask)...")
    try:
        app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)
    except Exception as e:
        print(f"❌ Error en Flask: {e}")

if __name__ == '__main__':
    print("=" * 60)
    print("🌿 SISTEMA INTEGRADO DE GESTIÓN E INVERNADERO PRO")
    print("=" * 60)
    
    # Creamos dos procesos independientes
    proceso_flask = Process(target=ejecutar_flask)
    proceso_spark = Process(target=ejecutar_streamlit)

    try:
        # Iniciar ambos
        proceso_flask.start()
        time.sleep(2)  # Pequeña pausa para no saturar la consola
        proceso_spark.start()

        print("\n✅ AMBOS SISTEMAS ESTÁN CORRIENDO:")
        print("🔗 App Principal:  http://localhost:5000")
        print("🔗 Dashboard ML:   http://localhost:8501")
        print("=" * 60)
        print("Presiona Ctrl+C para detener ambos servidores.\n")

        # Mantener el script vivo mientras los procesos corran
        proceso_flask.join()
        proceso_spark.join()

    except KeyboardInterrupt:
        print("\n🛑 Deteniendo servidores...")
        proceso_flask.terminate()
        proceso_spark.terminate()
        print("✅ Sistemas cerrados correctamente.")