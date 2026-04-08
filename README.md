```markdown

##🌱 Sistema de Gestión de Plantas

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.0+-000000?style=for-the-badge&logo=flask&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?style=for-the-badge&logo=mysql&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.0-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white)

Sistema web completo para gestión de plantas, riegos automáticos, respaldos de base de datos y tienda online. Desarrollado con Flask, MySQL y Bootstrap 5.

---

## 📋 Tabla de Contenidos
- [Características](#-características)
- [Requisitos Previos](#-requisitos-previos)
- [Instalación Paso a Paso](#-instalación-paso-a-paso)
- [Configuración de Base de Datos](#-configuración-de-base-de-datos)
- [Estructura del Proyecto](#-estructura-del-proyecto)
- [Ejecución del Sistema](#-ejecución-del-sistema)
- [Acceso al Sistema](#-acceso-al-sistema)
- [Funcionalidades](#-funcionalidades-detalladas)
- [Solución de Problemas](#-solución-de-problemas)
- [Contribución](#-contribución)

---

## ✨ Características

### 🏠 Dashboard Principal
* Estadísticas en tiempo real de plantas y riegos.
* Últimos riegos registrados.
* Estado de respaldos (para administradores).

### 🌿 Gestión de Plantas
* CRUD completo de plantas (Crear, Leer, Actualizar, Eliminar).
* Registro de riegos con cantidad, tipo y notas.
* Seguimiento del historial de riegos.
* Estados personalizados para cada planta.

### 💾 Sistema de Respaldos
* Respaldos automáticos de base de datos.
* Tipos de respaldo: Completo, Diferencial, Mínima modificación.
* Verificación de integridad con **checksum SHA-256**.
* Restauración de respaldos e interfaz web para gestión.

### 🛒 Tienda Online (Rol Cliente)
* Catálogo de plantas disponibles para venta.
* Filtros por categoría y precio.
* Carrito de compras y búsqueda avanzada.

### 👥 Sistema de Usuarios
* Roles: Administrador y Cliente.
* Autenticación segura con **Flask-Login**.
* Panel de administración exclusivo.

---

## 📋 Requisitos Previos

### Software Requerido
* **Python 3.8+** - [Descargar Python](https://www.python.org/)
* **XAMPP (Windows)** o MySQL/MariaDB - [Descargar XAMPP](https://www.apachefriends.org/)
* **Git** (Opcional)

### Verificación de Instalación
```bash
# Verificar Python
python --version

# Verificar pip
pip --version
```
*Nota: Asegúrate de que MySQL esté corriendo en tu panel de XAMPP.*

---

## 🚀 Instalación Paso a Paso

### Paso 1: Clonar o Descargar el Proyecto
**Opción A: Clonar con Git**
```bash
git clone [https://github.com/tuusuario/sistema_gestion_plantas.git](https://github.com/tuusuario/sistema_gestion_plantas.git)
cd sistema_gestion_plantas
```
**Opción B: Descargar ZIP**
* Descarga y extrae el archivo.
* Abre la terminal en esa carpeta.

### Paso 2: Crear Entorno Virtual
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### Paso 3: Instalar Dependencias
```bash
pip install -r requirements.txt

# Instalación manual si no existe el archivo:
pip install flask flask-sqlalchemy flask-login flask-wtf flask-migrate mysql-connector-python flask-mail python-dotenv
```

### Paso 4: Configurar MySQL (XAMPP)
1. Iniciar Apache y MySQL en XAMPP.
2. Acceder a phpMyAdmin y crear usuario si es necesario:
```sql
CREATE USER 'root'@'localhost' IDENTIFIED BY '';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost';
FLUSH PRIVILEGES;
```

---

## 🗄️ Configuración de Base de Datos

### Paso 1: Crear Base de Datos
```sql
CREATE DATABASE IF NOT EXISTS gestion_plantas 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;
```

### Paso 2: Configurar Conexión
En `config.py`, ajusta tus credenciales si usas contraseña:
```python
MYSQL_HOST = 'localhost'
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'tu_contraseña_aqui'
MYSQL_DATABASE = 'gestion_plantas'
```

### Paso 3: Crear Tablas
Ejecuta la aplicación por primera vez y las tablas se generarán automáticamente:
```bash
python run.py
```

---

## 📁 Estructura del Proyecto

```text
sistema_gestion_plantas/
├── app/
│   ├── __init__.py          # Inicialización
│   ├── models.py            # Modelos de BD
│   ├── routes.py            # Rutas
│   ├── templates/           # HTML (auth, plants, backups, tienda)
│   └── static/             # CSS, JS, imágenes
├── config.py               # Configuración
├── run.py                  # Ejecución principal
├── requirements.txt        # Dependencias
├── backups/                # Generado automáticamente
└── logs/                   # Generado automáticamente
```

---

## 🚀 Ejecución del Sistema

1. **Activar entorno:** `venv\Scripts\activate` (Windows).
2. **Ejecutar:** `python run.py`.
3. **Acceder:** Abrir navegador en `http://localhost:5000`.

**Salida esperada en consola:**
```text
==================================================
🌱 SISTEMA DE GESTIÓN DE PLANTAS
==================================================
✅ Directorio creado: backups
✅ Directorio creado: logs
✅ mysqldump encontrado en PATH
* Running on [http://127.0.0.1:5000](http://127.0.0.1:5000)
```

---

## 🔐 Acceso al Sistema

| Rol | Email | Contraseña | Acceso |
| :--- | :--- | :--- | :--- |
| **Administrador** | admin@plantas.com | Admin123! | Dashboard completo, respaldos, reportes |
| **Cliente** | cliente@plantas.com | Cliente123! | Solo tienda online |

**Crear usuarios manualmente (SQL):**
```sql
INSERT INTO usuarios (nombre, correo, rol, contrasenia_hash) 
VALUES ('Nuevo Admin', 'admin2@plantas.com', 'admin', 'hash_generado');
```

---

## 📊 Funcionalidades Detalladas

1. **Dashboard:** Estadísticas, últimos riegos y acciones rápidas.
2. **Gestión de Plantas:** Tarjetas visuales, edición y registro de riego detallado.
3. **Respaldos (Admin):** Checksum SHA-256 para integridad y restauración rápida.
4. **Tienda (Cliente):** Búsqueda avanzada y gestión de carrito.
5. **Reportes:** Auditoría de accesos y actividad de respaldos.

---

## 🔧 Solución de Problemas

> [!CAUTION]
> **Error: MySQL no está corriendo**
> Inicia MySQL desde el XAMPP Control Panel y verifica el puerto 3306.

> [!TIP]
> **Error: mysqldump no encontrado**
> Agrega `C:\xampp\mysql\bin` al PATH del sistema en Windows.

* **Puerto 5000 en uso:** Cambia el puerto en `run.py`: `app.run(debug=True, port=5001)`
* **ModuleNotFoundError:** Asegúrate de tener el entorno virtual activo e instalar los requisitos.

---

## 📦 Configuración para Producción

1. **Cambiar modo:** En `run.py`, `app = create_app('production')`.
2. **Servidor WSGI:**
```bash
pip install waitress
# Ejecutar con:
from waitress import serve
serve(app, host='0.0.0.0', port=8080)
```
3. **Variables de entorno:** Crea un archivo `.env` para llaves secretas y credenciales de correo.

---

## 🤝 Contribución
1. Haz un **Fork** del proyecto.
2. Crea una rama (`git checkout -b feature/mejora`).
3. Realiza tus **Commits** descriptivos.
4. Abre un **Pull Request**.

---

## 📝 Licencia
Este proyecto está bajo la Licencia **MIT**.

👨‍💻 **Soporte:** Crea un *issue* en el repositorio si encuentras errores.

---

## 🌟 Características Futuras
- [ ] Sistema de riegos automáticos programados.
- [ ] Notificaciones por email.
- [ ] API REST para apps móviles.
- [ ] Reportes en PDF/Excel.
```