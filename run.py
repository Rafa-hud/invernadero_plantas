# run.py
import os
import sys

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app import create_app
except ImportError as e:
    print(f"❌ Error de importación: {e}")
    print("\n🔧 Solución de problemas:")
    print("1. Asegúrate de que estás en el entorno virtual: venv\\Scripts\\activate")
    print("2. Instala las dependencias: pip install -r requirements.txt")
    print("3. Verifica la estructura de carpetas")
    input("\nPresiona Enter para salir...")
    sys.exit(1)

app = create_app('development')

if __name__ == '__main__':
    print("=" * 50)
    print("🌱 SISTEMA DE GESTIÓN DE PLANTAS")
    print("=" * 50)
    print(f"📁 Directorio: {os.path.abspath('.')}")
    print(f"🔧 Modo: {'Desarrollo' if app.debug else 'Producción'}")
    print(f"🌐 URL: http://localhost:5000")
    print("=" * 50)
    
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n🔧 Solución de problemas:")
        print("1. Verifica que MySQL/XAMPP esté corriendo")
        print("2. Verifica el puerto 5000 no esté en uso")
        print("3. Revisa los logs en la carpeta 'logs/'")
        input("\nPresiona Enter para salir...")