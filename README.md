🌱 Sistema de Gestión de Plantas
Sistema web completo para gestión de plantas, riegos automáticos, respaldos de base de datos y tienda online. Desarrollado con Flask, MySQL y Bootstrap 5.

📋 Tabla de Contenidos
Características

Requisitos Previos

Instalación Paso a Paso

Configuración de Base de Datos

Estructura del Proyecto

Ejecución del Sistema

Acceso al Sistema

Funcionalidades

Solución de Problemas

Contribución

✨ Características
🏠 Dashboard Principal
Estadísticas en tiempo real de plantas y riegos

Últimos riegos registrados

Estado de respaldos (para administradores)

🌿 Gestión de Plantas
CRUD completo de plantas (Crear, Leer, Actualizar, Eliminar)

Registro de riegos con cantidad, tipo y notas

Seguimiento del historial de riegos

Estados personalizados para cada planta

💾 Sistema de Respaldos
Respaldos automáticos de base de datos

Tipos de respaldo: Completo, Diferencial, Mínima modificación

Verificación de integridad con checksum SHA-256

Restauración de respaldos

Interfaz web para gestión de respaldos

🛒 Tienda Online (Rol Cliente)
Catálogo de plantas disponibles para venta

Filtros por categoría y precio

Carrito de compras

Detalles de cada planta con imágenes

Búsqueda avanzada

👥 Sistema de Usuarios
Roles: Administrador y Cliente

Autenticación segura con Flask-Login

Historial de accesos

Panel de administración exclusivo

📋 Requisitos Previos
Software Requerido
Python 3.8 o superior - Descargar Python

XAMPP (Windows) o MySQL/MariaDB - Descargar XAMPP

Git (opcional) - Descargar Git

Verificación de Instalación
bash
# Verificar Python
python --version

# Verificar pip (gestor de paquetes de Python)
pip --version

# Verificar MySQL (en XAMPP)
# Abrir XAMPP Control Panel y hacer clic en "Start" en MySQL
🚀 Instalación Paso a Paso
Paso 1: Clonar o Descargar el Proyecto
Opción A: Clonar con Git
bash
# Clonar el repositorio
git clone https://github.com/tuusuario/sistema_gestion_plantas.git

# Acceder al directorio
cd sistema_gestion_plantas
Opción B: Descargar ZIP
Descargar el proyecto como ZIP

Extraer en una carpeta de tu elección

Abrir terminal en esa carpeta

Paso 2: Crear Entorno Virtual
bash
# Crear entorno virtual (Windows)
python -m venv venv

# Activar entorno virtual (Windows)
venv\Scripts\activate

# Crear entorno virtual (Linux/Mac)
python3 -m venv venv

# Activar entorno virtual (Linux/Mac)
source venv/bin/activate
Nota: Deberías ver (venv) al inicio de tu línea de comandos.

Paso 3: Instalar Dependencias
bash
# Instalar todas las dependencias
pip install -r requirements.txt

# Si no tienes requirements.txt, instalar manualmente:
pip install flask flask-sqlalchemy flask-login flask-wtf flask-migrate mysql-connector-python flask-mail python-dotenv
Paso 4: Configurar XAMPP (Windows)
Iniciar XAMPP Control Panel

Hacer clic en "Start" junto a Apache y MySQL

Abrir phpMyAdmin (http://localhost/phpmyadmin)

Crear usuario (si es necesario):

sql
CREATE USER 'root'@'localhost' IDENTIFIED BY '';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost';
FLUSH PRIVILEGES;
🗄️ Configuración de Base de Datos
Paso 1: Crear Base de Datos
sql
-- En phpMyAdmin o MySQL Workbench ejecutar:
CREATE DATABASE IF NOT EXISTS gestion_plantas 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

-- Verificar que se creó
SHOW DATABASES;
Paso 2: Configurar Conexión
El archivo config.py ya está configurado para XAMPP con estas credenciales:

python
# Configuración por defecto para XAMPP:
MYSQL_HOST = 'localhost'
MYSQL_USER = 'root'
MYSQL_PASSWORD = ''  # Contraseña vacía por defecto en XAMPP
MYSQL_DATABASE = 'gestion_plantas'
Si usas contraseña en MySQL, edita config.py:

python
MYSQL_PASSWORD = 'tu_contraseña_aqui'
Paso 3: Crear Tablas Automáticamente
bash
# Ejecutar la aplicación por primera vez
python run.py
Las tablas se crearán automáticamente cuando inicies la aplicación por primera vez.

📁 Estructura del Proyecto
text
sistema_gestion_plantas/
├── app/
│   ├── __init__.py          # Inicialización de la aplicación
│   ├── models.py            # Modelos de base de datos
│   ├── routes.py            # Rutas y controladores
│   ├── templates/           # Plantillas HTML
│   │   ├── auth/           # Login y autenticación
│   │   ├── plants/         # Gestión de plantas
│   │   ├── backups/        # Gestión de respaldos
│   │   ├── tienda/         # Tienda online
│   │   ├── dashboard.html  # Panel principal
│   │   └── base.html       # Plantilla base
│   └── static/             # CSS, JS, imágenes
├── config.py               # Configuración de la aplicación
├── run.py                  # Archivo de ejecución
├── requirements.txt        # Dependencias de Python
├── backups/               # Respaldos de base de datos (se crea automático)
├── logs/                  # Archivos de log (se crea automático)
└── README.md              # Este archivo
🚀 Ejecución del Sistema
Paso 1: Activar Entorno Virtual
bash
# En la carpeta del proyecto
venv\Scripts\activate  # Windows
# o
source venv/bin/activate  # Linux/Mac
Paso 2: Ejecutar la Aplicación
bash
python run.py
Paso 3: Acceder al Sistema
Abrir navegador y visitar: http://localhost:5000

Salida Esperada en Consola
text
==================================================
🌱 SISTEMA DE GESTIÓN DE PLANTAS
==================================================
📁 Directorio base: C:\sistema_gestion_plantas
🔧 Modo: Desarrollo
🌐 URL: http://localhost:5000
==================================================
✅ Directorio creado: backups
✅ Directorio creado: logs
✅ mysqldump encontrado en PATH del sistema
📋 Configuración MySQL:
   Host: localhost
   Usuario: root
   Base de datos: gestion_plantas
   Puerto: 3306
   Carpeta respaldos: backups
 * Running on http://0.0.0.0:5000
 * Debug mode: on
🔐 Acceso al Sistema
Usuarios por Defecto
Rol	Email	Contraseña	Acceso
Administrador	admin@plantas.com	Admin123!	Dashboard completo, respaldos, reportes
Cliente	cliente@plantas.com	Cliente123!	Solo tienda online
Nota: El usuario administrador se crea automáticamente al iniciar por primera vez.

Crear Nuevos Usuarios
sql
-- Insertar usuario administrador
INSERT INTO usuarios (nombre, correo, rol, contrasenia_hash) 
VALUES ('Nuevo Admin', 'admin2@plantas.com', 'admin', 'hash_generado');

-- Insertar usuario cliente
INSERT INTO usuarios (nombre, correo, rol, contrasenia_hash) 
VALUES ('Nuevo Cliente', 'cliente2@plantas.com', 'cliente', 'hash_generado');
📊 Funcionalidades Detalladas
1. Dashboard Principal
Estadísticas: Total de plantas, riegos pendientes

Últimos riegos: Tabla con los 10 riegos más recientes

Acciones rápidas: Enlaces directos a funciones comunes

2. Gestión de Plantas
Listar plantas: Vista en tarjetas o tabla

Agregar planta: Formulario con validación

Editar planta: Modificar información existente

Eliminar planta: Con confirmación

Registrar riego: Con fecha, cantidad, tipo y notas

Historial de riegos: Ver todos los riegos de una planta

3. Sistema de Respaldos (Solo Admin)
Crear respaldo: Completo, diferencial o mínima modificación

Listar respaldos: Tabla con información detallada

Restaurar respaldo: Recuperar base de datos

Verificar integridad: Checksum SHA-256

Eliminar respaldo: Con confirmación

4. Tienda Online (Solo Clientes)
Catálogo: Plantas disponibles para venta

Filtros: Por categoría, precio y disponibilidad

Búsqueda: Por nombre, especie o descripción

Detalles: Información completa de cada planta

Carrito: Gestión de compras (esqueleto)

5. Reportes (Solo Admin)
Reporte de respaldos: Estadísticas y actividad

Reporte de accesos: Historial de usuarios

🔧 Solución de Problemas
Error 1: "MySQL no está corriendo"
text
❌ Error al conectar con MySQL
Solución:

Abrir XAMPP Control Panel

Hacer clic en "Start" junto a MySQL

Verificar que el puerto 3306 esté libre

Error 2: "Base de datos no existe"
text
OperationalError: (1049, "Unknown database 'gestion_plantas'")
Solución:

sql
-- Crear base de datos manualmente
CREATE DATABASE gestion_plantas;
Error 3: "mysqldump no encontrado"
text
Error al ejecutar mysqldump
Solución:

Verificar que MySQL esté instalado

Agregar MySQL al PATH del sistema

En Windows con XAMPP, agregar: C:\xampp\mysql\bin

Error 4: "ModuleNotFoundError"
text
ModuleNotFoundError: No module named 'flask'
Solución:

bash
# Activar entorno virtual
venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
Error 5: "Puerto 5000 en uso"
text
OSError: [Errno 98] Address already in use
Solución:

bash
# Cambiar puerto en run.py
app.run(debug=True, port=5001)

# O matar proceso usando el puerto
# Windows:
netstat -ano | findstr :5000
taskkill /PID [PID] /F

# Linux/Mac:
lsof -i :5000
kill -9 [PID]
🐛 Debug Mode
Para activar modo debug y ver errores detallados:

python
# En run.py
app.run(debug=True, host='0.0.0.0', port=5000)
Características del modo debug:

Recarga automática al cambiar código

Debugger interactivo en el navegador

Mensajes de error detallados

📦 Configuración para Producción
1. Cambiar Configuración
python
# En run.py
app = create_app('production')

# En config.py cambiar:
SESSION_COOKIE_SECURE = True  # Solo con HTTPS
DEBUG = False
2. Configurar HTTPS
python
# Usar servidor WSGI como Waitress o Gunicorn
pip install waitress

# run_production.py
from waitress import serve
from app import create_app

app = create_app('production')
serve(app, host='0.0.0.0', port=8080)
3. Variables de Entorno
Crear archivo .env:

env
SECRET_KEY=clave-muy-segura-y-unica
DATABASE_URL=mysql+mysqlconnector://user:password@localhost/gestion_plantas
MAIL_USERNAME=tu-email@gmail.com
MAIL_PASSWORD=tu-contraseña-email
🤝 Contribución
Reportar Issues
Verificar si el problema ya está reportado

Incluir pasos para reproducir

Especificar entorno (OS, Python, MySQL versiones)

Enviar Pull Requests
Fork del repositorio

Crear rama para la funcionalidad

Commits descriptivos

Tests si aplica

Documentar cambios

Estilo de Código
PEP 8 para Python

Comentarios en inglés o español

Nombres descriptivos de variables

📝 Licencia
Este proyecto está bajo la Licencia MIT. Ver archivo LICENSE para más detalles.

👨‍💻 Soporte
Para soporte:

Revisar la sección Solución de Problemas

Crear issue en el repositorio

Contactar al mantenedor

🌟 Características Futuras
Sistema de riegos automáticos programados

Notificaciones por email

API REST para aplicaciones móviles

Reportes PDF/Excel

Integración con sistemas de pago

App móvil con Flutter/React Native

