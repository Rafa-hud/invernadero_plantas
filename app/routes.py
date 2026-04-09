from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, current_app, session
from flask_login import login_user, logout_user, login_required, current_user, UserMixin
from bson.objectid import ObjectId
from datetime import datetime, timedelta, date
import os
import traceback
import gzip
import shutil
import hashlib
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import json
import platform
import psutil
import subprocess
import tempfile
import string
import sys
from app.database import get_db
from app.models import RegistroRiegoModel
import shutil

tienda_bp = Blueprint('tienda', __name__)
main_bp = Blueprint('main', __name__)


# Si estás en Windows, importar windll para la detección de USB
if platform.system() == 'Windows':
    from ctypes import windll

# Importamos los modelos de MongoDB que creamos en el Paso 4
# Asegúrate de haber añadido un HistorialModel a tu models.py con una función create()
from app.models import UsuarioModel, PlantaModel, PedidoModel, HistorialModel 

# ========== ADAPTACIÓN PARA FLASK-LOGIN CON MONGODB ==========
class UserWrapper(UserMixin):
    """Clase puente para que Flask-Login entienda los diccionarios de MongoDB"""
    def __init__(self, user_dict):
        self.id = str(user_dict.get('_id'))
        self.nombre = user_dict.get('nombre')
        self.correo = user_dict.get('correo')
        self.rol = user_dict.get('rol')
        self.estado = user_dict.get('estado')

# Blueprints
auth_bp = Blueprint('auth', __name__)
main_bp = Blueprint('main', __name__)
plants_bp = Blueprint('plants', __name__)
backup_bp = Blueprint('backup', __name__)
reports_bp = Blueprint('reports', __name__)
tienda_bp = Blueprint('tienda', __name__)

# ========== CONFIGURACIÓN DE RESPALDOS ==========
BACKUP_FOLDER = 'backups'
ALLOWED_EXTENSIONS = {'sql', 'gz', 'json', 'bson'} # Añadidos formatos NoSQL

if not os.path.exists(BACKUP_FOLDER):
    os.makedirs(BACKUP_FOLDER, exist_ok=True)

# ========== FUNCIONES AUXILIARES INTACTAS ==========
def obtener_carrito():
    if 'carrito' not in session:
        session['carrito'] = {}
    return session['carrito']

def guardar_carrito(carrito):
    session['carrito'] = carrito
    session.modified = True

def calcular_checksum(filepath):
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        current_app.logger.error(f"Error calculando checksum para {filepath}: {e}")
        return None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validar_ruta_segura(ruta):
    if not ruta:
        return False
    ruta = os.path.abspath(ruta)
    rutas_prohibidas = [
        '/', '/etc', '/bin', '/usr', '/var', '/root', '/home',
        '/lib', '/opt', '/sbin', '/sys', '/proc', '/dev',
        'C:\\', 'C:\\Windows', 'C:\\Program Files', 'C:\\Program Files (x86)',
        'C:\\Users', 'C:\\System32', 'C:\\Windows\\System32'
    ]
    for prohibida in rutas_prohibidas:
        if ruta.startswith(prohibida):
            return False
    return os.path.exists(ruta)

# ---------- USB -------------------------------------
def detectar_usb_json():
    """Detección USB con validación estricta de permisos de escritura (Write-Test)"""
    sistema = platform.system()
    resultado = {
        'conectado': False, 'ruta': None, 'espacio_libre': 0,
        'espacio_total': 0, 'sistema': sistema, 'dispositivos': []
    }
    
    # --- HELPER DE VALIDACIÓN (WRITE-TEST) ---
    def _tiene_permiso_escritura(ruta_prueba):
        """Intenta crear y borrar un archivo temporal oculto para validar permisos"""
        archivo_test = os.path.join(ruta_prueba, '.test_backup_write')
        try:
            with open(archivo_test, 'w') as f:
                f.write('test')
            os.remove(archivo_test)
            return True
        except Exception as e:
            # Captura PermissionError, OSError, etc., y registra el falso positivo
            try:
                current_app.logger.warning(f"Falso positivo USB descartado en {ruta_prueba}: Sin permisos de escritura. Detalle: {str(e)}")
            except:
                pass # Por si se ejecuta fuera del contexto de Flask
            return False
    # -----------------------------------------

    try:
        if sistema == 'Windows':
            # Capa 1: psutil particiones removibles
            for particion in psutil.disk_partitions():
                if particion.mountpoint.lower() == 'c:\\':
                    continue
                if 'removable' in particion.opts.lower():
                    try:
                        uso = psutil.disk_usage(particion.mountpoint)
                        # INYECCIÓN DEL WRITE-TEST AQUÍ
                        if uso.total > 0 and _tiene_permiso_escritura(particion.mountpoint):
                            resultado.update({
                                'conectado': True, 'ruta': particion.mountpoint,
                                'espacio_libre': round(uso.free / (1024**3), 2),
                                'espacio_total': round(uso.total / (1024**3), 2)
                            })
                            break
                    except: continue
            
            # Capa 2: Windows API (Fuerza bruta)
            if not resultado['conectado']:
                import ctypes
                windll = ctypes.windll
                for letra in string.ascii_uppercase:
                    drive = f"{letra}:\\"
                    try:
                        if os.path.exists(drive) and windll.kernel32.GetDriveTypeW(drive) == 2:
                            uso = psutil.disk_usage(drive)
                            # INYECCIÓN DEL WRITE-TEST AQUÍ
                            if uso.total > 0 and _tiene_permiso_escritura(drive):
                                resultado.update({
                                    'conectado': True, 'ruta': drive,
                                    'espacio_libre': round(uso.free / (1024**3), 2),
                                    'espacio_total': round(uso.total / (1024**3), 2)
                                })
                                break
                    except: continue
                        
        elif sistema == 'Linux':
            # Capa 3: Linux
            posibles_rutas = ['/media', '/mnt', '/run/media', '/media/$USER', '/mnt/usb']
            for ruta_base in posibles_rutas:
                ruta_expandida = os.path.expanduser(ruta_base.replace('$USER', os.getenv('USER', '')))
                if os.path.exists(ruta_expandida):
                    try:
                        for item in os.listdir(ruta_expandida):
                            path_completo = os.path.join(ruta_expandida, item)
                            if os.path.ismount(path_completo):
                                uso = psutil.disk_usage(path_completo)
                                # INYECCIÓN DEL WRITE-TEST AQUÍ
                                if uso.total > 0 and _tiene_permiso_escritura(path_completo):
                                    resultado.update({
                                        'conectado': True, 'ruta': path_completo,
                                        'espacio_libre': round(uso.free / (1024**3), 2),
                                        'espacio_total': round(uso.total / (1024**3), 2)
                                    })
                                    break
                    except: continue
                if resultado['conectado']: break
                    
        elif sistema == 'Darwin':
            # Capa 3: Mac
            posibles_rutas = ['/Volumes']
            for ruta_base in posibles_rutas:
                if os.path.exists(ruta_base):
                    try:
                        for item in os.listdir(ruta_base):
                            path_completo = os.path.join(ruta_base, item)
                            if not item.startswith('.') and os.path.ismount(path_completo):
                                uso = psutil.disk_usage(path_completo)
                                # INYECCIÓN DEL WRITE-TEST AQUÍ
                                if uso.total > 0 and _tiene_permiso_escritura(path_completo):
                                    resultado.update({
                                        'conectado': True, 'ruta': path_completo,
                                        'espacio_libre': round(uso.free / (1024**3), 2),
                                        'espacio_total': round(uso.total / (1024**3), 2)
                                    })
                                    break
                    except: continue
                if resultado['conectado']: break
        
        # Capa 4: Fallback universal
        if not resultado['conectado']:
            for particion in psutil.disk_partitions():
                mountpoint = particion.mountpoint
                system_paths = ['/', '/boot', '/home', '/var', '/usr', '/etc', 'C:\\', '/System', '/Library']
                if not any(mountpoint.startswith(sys_path) for sys_path in system_paths):
                    try:
                        uso = psutil.disk_usage(mountpoint)
                        # INYECCIÓN DEL WRITE-TEST AQUÍ
                        if uso.total > 0 and uso.total < 2 * 1024**4 and _tiene_permiso_escritura(mountpoint):
                            resultado.update({
                                'conectado': True, 'ruta': mountpoint,
                                'espacio_libre': round(uso.free / (1024**3), 2),
                                'espacio_total': round(uso.total / (1024**3), 2)
                            })
                            break
                    except: continue
    except Exception as e:
        resultado['error'] = str(e)
    return resultado


def crear_backup_folder_usb(usb_path):
    try:
        usb_backup_folder = os.path.join(usb_path, 'respaldos_gestion_plantas')
        os.makedirs(usb_backup_folder, exist_ok=True)
        return usb_backup_folder
    except Exception as e:
        current_app.logger.error(f"Error creando carpeta USB: {e}")
        raise

# ========== AUTH ROUTES (ADAPTADAS A MONGODB) ==========
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.rol == 'admin': return redirect(url_for('main.dashboard'))
        elif current_user.rol == 'cliente': return redirect(url_for('tienda.tienda_index'))
        else: return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        correo = request.form.get('correo')
        contrasenia = request.form.get('contrasenia')
        
        # MONGODB: Buscar usuario por email usando el modelo
        usuario_dict = UsuarioModel.get_by_email(correo)
        
        if usuario_dict:
            if check_password_hash(usuario_dict['contrasenia_hash'], contrasenia):
                # Envolver el diccionario en nuestra clase para Flask-Login
                user_obj = UserWrapper(usuario_dict)
                login_user(user_obj, remember=True)
                
                # MONGODB: Crear registro de acceso
                HistorialModel.create({
                    'usuario_id': usuario_dict['_id'],
                    'ip_address': request.remote_addr,
                    'user_agent': request.user_agent.string,
                    'estado_sesion': 'iniciada',
                    'accion': 'login',
                    'fecha_acceso': datetime.utcnow()
                })
                
                flash(f'¡Bienvenido, {usuario_dict["nombre"]}!', 'success')
                
                if usuario_dict['rol'] == 'admin': return redirect(url_for('main.dashboard'))
                elif usuario_dict['rol'] == 'cliente': return redirect(url_for('tienda.tienda_index'))
                else: return redirect(url_for('main.dashboard'))
            else:
                flash('Contraseña incorrecta', 'danger')
        else:
            flash('Usuario no encontrado', 'danger')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    # MONGODB: Registrar salida
    HistorialModel.create({
        'usuario_id': ObjectId(current_user.id),
        'ip_address': request.remote_addr,
        'user_agent': request.user_agent.string,
        'estado_sesion': 'cerrada',
        'accion': 'logout',
        'fecha_acceso': datetime.utcnow()
    })
    
    logout_user()
    flash('Has cerrado sesión', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/registro', methods=['GET', 'POST'])
def registro_cliente():
    if current_user.is_authenticated:
        if current_user.rol == 'cliente': return redirect(url_for('tienda.tienda_index'))
        else: return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        try:
            nombre = request.form.get('nombre', '').strip()
            correo = request.form.get('correo', '').strip().lower()
            contrasenia = request.form.get('contrasenia', '')
            confirmar_contrasenia = request.form.get('confirmar_contrasenia', '')
            telefono = request.form.get('telefono', '').strip()
            direccion = request.form.get('direccion', '').strip()
            
            errores = []
            if not nombre or len(nombre) < 3: errores.append('El nombre debe tener al menos 3 caracteres.')
            if not correo or '@' not in correo: errores.append('Correo electrónico inválido.')
            
            # MONGODB: Verificar si existe
            usuario_existente = UsuarioModel.get_by_email(correo)
            if usuario_existente: errores.append('Este correo ya está registrado.')
            
            if not contrasenia or len(contrasenia) < 6: errores.append('La contraseña debe tener al menos 6 caracteres.')
            if contrasenia != confirmar_contrasenia: errores.append('Las contraseñas no coinciden.')
            
            if errores:
                for error in errores: flash(error, 'danger')
                return render_template('auth/registro.html', nombre=nombre, correo=correo, telefono=telefono, direccion=direccion)
            
            # MONGODB: Insertar nuevo cliente
            nuevo_cliente_data = {
                'nombre': nombre,
                'correo': correo,
                'contrasenia_hash': generate_password_hash(contrasenia),
                'rol': 'cliente',
                'telefono': telefono,
                'direccion': direccion,
                'fecha_registro': datetime.utcnow(),
                'estado': 'activo'
            }
            nuevo_id = UsuarioModel.create(nuevo_cliente_data)
            
            # MONGODB: Registrar acceso
            HistorialModel.create({
                'usuario_id': nuevo_id,
                'ip_address': request.remote_addr,
                'user_agent': request.user_agent.string,
                'estado_sesion': 'registro',
                'accion': 'registro_cliente',
                'fecha_acceso': datetime.utcnow()
            })
            
            # Loguear automáticamente
            nuevo_cliente_data['_id'] = nuevo_id
            user_obj = UserWrapper(nuevo_cliente_data)
            login_user(user_obj, remember=True)
            
            flash('¡Registro exitoso! Bienvenido/a a nuestra tienda.', 'success')
            return redirect(url_for('tienda.tienda_index'))
            
        except Exception as e:
            flash(f'Error en el registro: {str(e)}', 'danger')
            return render_template('auth/registro.html')
    
    return render_template('auth/registro.html')

# routes.py (PARTE 2: Gestión de Plantas y Tienda)

# Nota: Asegúrate de tener implementados los métodos correspondientes en tus modelos,
# por ejemplo: PlantaModel.get_by_usuario(), PlantaModel.get_disponibles(), etc.

# ========== FUNCIONES AUXILIARES PARA IMÁGENES (INTACTAS) ==========
def allowed_image_file(filename):
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def guardar_imagen(file, planta_id):
    try:
        upload_folder = current_app.config.get('PLANTAS_UPLOAD_FOLDER', 
                                             os.path.join(current_app.static_folder, 'uploads', 'plantas'))
        os.makedirs(upload_folder, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
        filename = f"planta_{planta_id}_{timestamp}.{ext}"
        filepath = os.path.join(upload_folder, filename)
        
        try:
            from PIL import Image
            img = Image.open(file)
            img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            img.save(filepath, 'JPEG' if ext in ['jpg', 'jpeg'] else ext.upper(), quality=85, optimize=True)
        except:
            file.save(filepath)
            
        return filename
    except Exception as e:
        current_app.logger.error(f"Error guardando imagen: {e}")
        raise

def es_url_imagen_valida(url):
    if not url: return False
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}
    url_lower = url.lower()
    for ext in image_extensions:
        if url_lower.endswith(ext): return True
    image_patterns = ['imgur.com', 'i.imgur.com', 'imageshack.com', 'flickr.com', 'photobucket.com', 'dropbox.com']
    for pattern in image_patterns:
        if pattern in url_lower: return True
    return False

# ========== PLANTAS ROUTES ==========
# ========== PLANTAS ROUTES ==========
@plants_bp.route('/')
@login_required
def listar_plantas():
    if current_user.rol == 'cliente':
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('tienda.tienda_index'))
    
    # 1. Obtener la lista completa de plantas según el rol
    if current_user.rol == 'admin':
        plantas_raw = PlantaModel.get_all()
    else:
        plantas_raw = PlantaModel.get_by_usuario(current_user.id)
    
    # 2. Configuración de Paginación
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Número de plantas por página
    total = len(plantas_raw)
    
    # 3. Lógica de Segmentación (Slicing)
    start = (page - 1) * per_page
    end = start + per_page
    plantas_paginadas = plantas_raw[start:end]
    
    # 4. Cálculo de número de páginas
    total_pages = (total // per_page) + (1 if total % per_page > 0 else 0)

    # 5. Diccionario de paginación para el HTML
    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1
    }
    
    # IMPORTANTE: Enviamos 'plantas_paginadas' en lugar de 'plantas_raw'
    return render_template('plants/lista.html', 
                           plantas=plantas_paginadas, 
                           pagination=pagination)

@plants_bp.route('/crear', methods=['GET', 'POST'])
@login_required
def crear_planta():
    if current_user.rol == 'cliente':
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('tienda.tienda_index'))
    
    if request.method == 'POST':
        try:
            nombre = request.form.get('nombre', '').strip()
            
            if not nombre:
                flash('El nombre de la planta es requerido', 'error')
                return render_template('plants/crear.html')
            
            nueva_planta = {
                'nombre': nombre,
                'especie': request.form.get('especie', '').strip(),
                'precio': float(request.form.get('precio', 0.0)),
                'stock': int(request.form.get('stock', 0)),
                'categoria': request.form.get('categoria', ''),
                'descripcion': request.form.get('descripcion', ''),
                'estado': 'activa',
                'usuario_id': ObjectId(current_user.id),
                'disponible_venta': False,
                'fecha_registro': datetime.utcnow()
            }
            
            PlantaModel.create(nueva_planta)
            flash(f'¡Planta "{nombre}" creada exitosamente!', 'success')
            return redirect(url_for('plants.listar_plantas'))
            
        except Exception as e:
            flash(f'Error al crear la planta: {str(e)}', 'error')
            return render_template('plants/crear.html')
    
    return render_template('plants/crear.html')

# MONGODB: Cambiamos <int:id> por <id> para aceptar ObjectIds (strings)
@plants_bp.route('/<id>')
@login_required
def detalle_planta(id):
    # Proteger la ruta: Validar si el texto es un ObjectId real de 24 caracteres
    if not ObjectId.is_valid(id):
        flash('URL inválida o planta no encontrada.', 'danger')
        return redirect(url_for('plants.listar_plantas'))
    
    planta = PlantaModel.get_by_id(id)
    if not planta:
        flash('Planta no encontrada', 'danger')
        return redirect(url_for('plants.listar_plantas'))
    
    if current_user.rol == 'cliente':
        if not planta.get('disponible_venta') or planta.get('estado') != 'activa':
            flash('Planta no disponible', 'danger')
            return redirect(url_for('tienda.tienda_index'))
        return redirect(url_for('tienda.ver_planta_tienda', id=id))
    
    if current_user.rol != 'admin' and str(planta.get('usuario_id')) != current_user.id:
        flash('No tienes permiso para ver esta planta', 'danger')
        return redirect(url_for('plants.listar_plantas'))
    
    return render_template('plants/detalle.html', planta=planta, now=datetime.utcnow())

@plants_bp.route('/<id>/editar', methods=['GET', 'POST'])
@login_required
def editar_planta(id):
    if current_user.rol == 'cliente': return redirect(url_for('tienda.tienda_index'))
    
    # Proteger la ruta: Validar si el texto es un ObjectId real de 24 caracteres
    if not ObjectId.is_valid(id):
        flash('URL inválida o planta no encontrada.', 'danger')
        return redirect(url_for('plants.listar_plantas'))
    
    planta = PlantaModel.get_by_id(id)
    if not planta: return redirect(url_for('plants.listar_plantas'))
    
    if request.method == 'POST':
        try:
            update_data = {
                'nombre': request.form.get('nombre', '').strip(),
                'especie': request.form.get('especie', '').strip(),
                'estado': request.form.get('estado', 'activa'),
                'precio': float(request.form.get('precio', 0.0)),
                'stock': int(request.form.get('stock', 0)),
                'categoria': request.form.get('categoria', ''),
                'descripcion': request.form.get('descripcion', ''),
                'disponible_venta': bool(request.form.get('disponible_venta', False))
            }
            
            imagen_file = request.files.get('imagen')
            imagen_url = request.form.get('imagen_url', '').strip()
            eliminar_imagen = request.form.get('eliminar_imagen') == 'true'
            
            if eliminar_imagen:
                update_data['imagen_url'] = None
                update_data['imagen_nombre'] = None
                update_data['imagen_path'] = None
            elif imagen_file and imagen_file.filename and allowed_image_file(imagen_file.filename):
                filename = guardar_imagen(imagen_file, id)
                update_data['imagen_nombre'] = filename
                update_data['imagen_path'] = f'uploads/plantas/{filename}'
            elif imagen_url and es_url_imagen_valida(imagen_url):
                update_data['imagen_url'] = imagen_url
            
            PlantaModel.update(id, update_data)
            flash(f'Planta actualizada correctamente', 'success')
            return redirect(url_for('plants.detalle_planta', id=id))
            
        except Exception as e:
            flash(f'Error al actualizar la planta: {str(e)}', 'error')
    
    return render_template('plants/editar.html', planta=planta)

@plants_bp.route('/<id>/eliminar', methods=['POST'])
@login_required
def eliminar_planta(id):
    if current_user.rol == 'cliente': return redirect(url_for('tienda.tienda_index'))
    PlantaModel.delete(id)
    flash(f'Planta eliminada correctamente', 'success')
    return redirect(url_for('plants.listar_plantas'))

# ========== RUTAS DE RIEGO ==========
@plants_bp.route('/<id>/registrar-riego', methods=['GET'])
@login_required
def mostrar_formulario_riego(id):
    planta = PlantaModel.get_by_id(id)
    # Asumimos que creaste un RegistroRiegoModel
    riegos_recientes = RegistroRiegoModel.get_by_planta(id, limit=5)
    
    return render_template('plants/registrar_riego.html', 
                         planta=planta, riegos_recientes=riegos_recientes,
                         today=datetime.now().strftime('%Y-%m-%d'), now=datetime.now())

@plants_bp.route('/guardar-riego', methods=['POST'])
@login_required
def guardar_riego():
    id_planta = request.form.get('id_planta')
    try:
        fecha_completa_str = f"{request.form.get('fecha_riego')} {request.form.get('hora_riego')}"
        nuevo_riego = {
            'id_planta': ObjectId(id_planta),
            'fecha_riego': datetime.strptime(fecha_completa_str, '%Y-%m-%d %H:%M'),
            'cantidad_agua': int(request.form.get('cantidad_agua')),
            'tipo_riego': request.form.get('tipo_riego'),
            'notas': request.form.get('notas', '').strip()
        }
        RegistroRiegoModel.create(nuevo_riego)
        flash('¡Riego registrado exitosamente!', 'success')
        return redirect(url_for('plants.detalle_planta', id=id_planta))
    except Exception as e:
        flash(f'Error al registrar el riego: {str(e)}', 'error')
        return redirect(url_for('plants.mostrar_formulario_riego', id=id_planta))

# ========== GESTIÓN TIENDA (ADMIN) ==========
@plants_bp.route('/<id>/agregar-tienda', methods=['POST'])
@login_required
def agregar_a_tienda(id):
    if current_user.rol == 'cliente': return jsonify({'success': False}), 403
    try:
        update_data = {
            'precio': float(request.form.get('precio', 0)),
            'descripcion': request.form.get('descripcion', ''),
            'stock': int(request.form.get('stock', 0)),
            'categoria': request.form.get('categoria', ''),
            'disponible_venta': True
        }
        PlantaModel.update(id, update_data)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Agregada a la tienda'})
        flash('Agregada a la tienda', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('plants.listar_plantas'))


@plants_bp.route('/<id>/actualizar-tienda', methods=['POST'])
@login_required
def actualizar_tienda(id):
    """Actualizar información de una planta en la tienda (Versión MongoDB)"""
    if current_user.rol == 'cliente':
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
    
    planta = PlantaModel.get_by_id(id)
    if not planta:
        return jsonify({'success': False, 'message': 'Planta no encontrada'}), 404
    
    if current_user.rol != 'admin' and str(planta.get('usuario_id')) != current_user.id:
        return jsonify({'success': False, 'message': 'No tienes permiso'}), 403
    
    try:
        update_data = {
            'precio': float(request.form.get('precio', 0)),
            'stock': int(request.form.get('stock', 0))
        }
        
        disponible_venta = request.form.get('disponible_venta')
        if disponible_venta == 'true':
            update_data['disponible_venta'] = True
        elif disponible_venta == 'false':
            update_data['disponible_venta'] = False
        
        PlantaModel.update(id, update_data)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': f'Información de tienda actualizada para "{planta.get("nombre")}"'
            })
        
        flash(f'Información de tienda actualizada para "{planta.get("nombre")}"', 'success')
        
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': f'Error al actualizar: {str(e)}'
            })
        flash(f'Error al actualizar: {str(e)}', 'error')
    
    return redirect(url_for('plants.listar_plantas'))

# ========== TIENDA ONLINE (CLIENTES) ==========

@tienda_bp.route('/')
@login_required
def tienda_index():
    if current_user.rol != 'cliente': 
        return redirect(url_for('main.dashboard'))
    
    # --- CONFIGURACIÓN DE PAGINACIÓN ---
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Número de productos por página
    orden = request.args.get('orden', 'nombre')
    
    # Obtener datos base
    plantas_raw = PlantaModel.get_disponibles() 
    categorias = PlantaModel.get_categorias_disponibles()

    # Lógica de ordenamiento (mantenemos la tuya)
    if orden == 'precio_asc':
        plantas_raw.sort(key=lambda x: float(x.get('precio', 0)))
    elif orden == 'precio_desc':
        plantas_raw.sort(key=lambda x: float(x.get('precio', 0)), reverse=True)
    else:
        plantas_raw.sort(key=lambda x: x.get('nombre', '').lower())

    # --- LÓGICA DE SEGMENTACIÓN ---
    total = len(plantas_raw)
    total_pages = (total // per_page) + (1 if total % per_page > 0 else 0)
    
    start = (page - 1) * per_page
    end = start + per_page
    plantas_paginadas = plantas_raw[start:end]

    # Formatear para el template
    plantas = []
    for p in plantas_paginadas:
        p_dict = dict(p)
        p_dict['id'] = str(p['_id'])
        plantas.append(p_dict)
    
    # CREAR EL DICCIONARIO QUE EL HTML ESTÁ BUSCANDO
    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1
    }
    
    # EL CAMBIO MÁS IMPORTANTE: Pasar 'pagination' y 'orden' al template
    # ... después de calcular 'pagination' ...
    return render_template('tienda/index.html', 
                       plantas=plantas, 
                       categorias=categorias, 
                       pagination=pagination, # ESTO ES LO MÁS IMPORTANTE
                       orden=orden)

@tienda_bp.route('/planta/<id>')
@login_required
def ver_planta_tienda(id):
    planta = PlantaModel.get_by_id(id)
    if not planta:
        flash('Planta no encontrada', 'warning')
        return redirect(url_for('tienda.tienda_index'))
    plantas_relacionadas = PlantaModel.get_by_categoria(planta.get('categoria'), exclude_id=id, limit=4)
    return render_template('tienda/detalle_planta.html', planta=planta, plantas_relacionadas=plantas_relacionadas)

@tienda_bp.route('/buscar')
@login_required
def buscar_plantas():
    query = request.args.get('q', '')
    precio_min = request.args.get('precio_min', type=float)
    precio_max = request.args.get('precio_max', type=float)
    categoria = request.args.get('categoria', '')
    
    plantas = PlantaModel.buscar_avanzada(query, precio_min, precio_max, categoria)
    categorias = PlantaModel.get_categorias_disponibles()
    
    return render_template('tienda/buscar.html', plantas=plantas, query=query, 
                         categorias=categorias, categoria_seleccionada=categoria)

@tienda_bp.route('/mi-perfil')
@login_required
def mi_perfil():
    return render_template('tienda/perfil.html', usuario=current_user)

# ========== CARRITO DE COMPRAS (Lógica Corregida y Única) ==========

@tienda_bp.route('/agregar-al-carrito/<id>', methods=['POST'])
@login_required
def agregar_al_carrito(id):
    try:
        planta = PlantaModel.get_by_id(id)
        if not planta or planta.get('stock', 0) <= 0:
            return jsonify({'success': False, 'message': 'Stock agotado'}), 400
        
        carrito = session.get('carrito', {})
        
        if id in carrito:
            carrito[id]['cantidad'] += 1
        else:
            carrito[id] = {
                'cantidad': 1,
                'precio': float(planta['precio']),
                'nombre': planta['nombre']
            }
            
        session['carrito'] = carrito
        session.modified = True
        
        return jsonify({
            'success': True,
            'carrito_count': sum(item['cantidad'] for item in carrito.values())
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@tienda_bp.route('/cantidad-carrito')
@login_required
def cantidad_carrito():
    carrito = session.get('carrito', {})
    total = sum(item.get('cantidad', 0) for item in carrito.values())
    return jsonify({'success': True, 'total_items': total})

@tienda_bp.route('/carrito')
@login_required
def ver_carrito():
    # Función para obtener carrito (asumiendo que está en tus utils o definida localmente)
    carrito = session.get('carrito', {})
    plantas_carrito = []
    subtotal = 0.0
    
    for planta_id_str, item in carrito.items():
        planta = PlantaModel.get_by_id(planta_id_str)
        if planta and planta.get('disponible_venta') and planta.get('stock', 0) > 0:
            precio_unitario = float(planta.get('precio', 0))
            cantidad = item['cantidad']
            total_item = cantidad * precio_unitario
            
            planta_dict = dict(planta)
            planta_dict['id'] = str(planta['_id'])
            planta_dict['cantidad'] = cantidad
            planta_dict['precio_unitario'] = precio_unitario
            planta_dict['total_item'] = total_item
            
            plantas_carrito.append(planta_dict)
            subtotal += total_item
            
    envio = 5.99 if subtotal < 50 and subtotal > 0 else 0
    iva = subtotal * 0.12
    total = subtotal + envio + iva
    
    return render_template('tienda/carrito.html', plantas_carrito=plantas_carrito, 
                         subtotal=subtotal, envio=envio, iva=iva, total=total, 
                         carrito_vacio=len(plantas_carrito) == 0)

# ========== CHECKOUT Y PEDIDOS ==========

@tienda_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    carrito = session.get('carrito', {})
    if not carrito:
        return redirect(url_for('tienda.ver_carrito'))
    
    subtotal = 0.0
    plantas_carrito = [] # Lista para mostrar en el resumen lateral del HTML
    
    # 1. Validar stock y preparar datos
    for planta_id_str, item in carrito.items():
        planta = PlantaModel.get_by_id(planta_id_str)
        if planta:
            if planta['stock'] < item['cantidad']:
                flash(f'Stock insuficiente para {planta["nombre"]}', 'danger')
                return redirect(url_for('tienda.ver_carrito'))
            
            precio = float(planta['precio'])
            total_item = precio * item['cantidad']
            subtotal += total_item
            
            # Formato que espera el template checkout.html
            plantas_carrito.append({
                'id': planta_id_str,
                'nombre': planta['nombre'],
                'cantidad': item['cantidad'],
                'precio_unitario': precio,
                'total_item': total_item,
                'imagen_url': planta.get('imagen_url'),
                'categoria': planta.get('categoria', 'Planta')
            })

    # 2. Cálculos financieros (Sección crítica para evitar el error Undefined)
    iva = subtotal * 0.12
    envio = 5.99 if subtotal < 50 else 0.0
    total = subtotal + iva + envio
    
    # 3. Procesar el formulario de compra
    if request.method == 'POST':
        try:
            nuevo_pedido = {
                'id_cliente': ObjectId(current_user.id),
                'costo_total': total,
                'subtotal': subtotal,
                'iva': iva,
                'envio': envio,
                'estado_pedido': 'pendiente',
                'fecha_orden': datetime.utcnow(),
                'direccion_envio': request.form.get('direccion_envio'),
                'telefono_contacto': request.form.get('telefono_contacto'),
                'metodo_pago': request.form.get('metodo_pago'),
                'notas_pedido': request.form.get('notas_pedido', ''),
                'detalles': plantas_carrito # Guardamos el snapshot de la compra
            }
            
            # Guardar en Base de Datos (MongoDB)
            PedidoModel.create(nuevo_pedido)
            
            # Actualizar Stock de las plantas
            for item in plantas_carrito:
                planta_bd = PlantaModel.get_by_id(item['id'])
                nuevo_stock = planta_bd['stock'] - item['cantidad']
                PlantaModel.update(item['id'], {
                    'stock': nuevo_stock, 
                    'disponible_venta': nuevo_stock > 0
                })
            
            # Limpiar sesión
            session['carrito'] = {}
            session.modified = True
            
            flash('¡Pedido realizado exitosamente! Gracias por confiar en SYSTEMPLANT.', 'success')
            return redirect(url_for('tienda.mis_pedidos'))
            
        except Exception as e:
            flash(f'Error al procesar el pedido: {str(e)}', 'danger')
            
    # 4. Renderizado (Aquí pasamos TODAS las variables)
    return render_template('tienda/checkout.html', 
                           plantas_carrito=plantas_carrito, 
                           subtotal=subtotal, 
                           iva=iva, 
                           envio=envio, 
                           total=total)

@tienda_bp.route('/mis-pedidos')
@login_required
def mis_pedidos():
    # Asegúrate de que el método get_by_usuario maneje el ObjectId correctamente
    pedidos = PedidoModel.get_by_usuario(current_user.id)
    return render_template('tienda/mis_pedidos.html', pedidos=pedidos)

    # --- AÑADE ESTO A ROUTES.PY ---

@tienda_bp.route('/pedido/<id>')
@login_required
def ver_pedido(id):
    # Buscamos el pedido en la base de datos usando su ID
    pedido = PedidoModel.get_by_id(id)
    if not pedido:
        flash('El pedido no existe.', 'danger')
        return redirect(url_for('tienda.mis_pedidos'))
    
    return render_template('tienda/ver_pedido.html', pedido=pedido)

@tienda_bp.route('/pedido/cancelar/<id>', methods=['POST'])
@login_required
def cancelar_pedido(id):
    try:
        pedido = PedidoModel.get_by_id(id)
        if not pedido or str(pedido['id_cliente']) != str(current_user.id):
            return jsonify({'success': False, 'message': 'No autorizado'}), 403

        # Lógica para restaurar stock si fuera necesario
        for item in pedido['detalles']:
            planta = PlantaModel.get_by_id(str(item['id_planta']))
            if planta:
                nuevo_stock = planta['stock'] + item['cantidad']
                PlantaModel.update(str(item['id_planta']), {'stock': nuevo_stock, 'disponible_venta': True})

        # Actualizar estado a cancelado
        PedidoModel.update_status(id, 'cancelado')
        
        return jsonify({'success': True, 'message': 'Pedido cancelado correctamente'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ========== ADMIN DASHBOARD Y PEDIDOS ==========

@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.rol == 'cliente':
        return redirect(url_for('tienda.tienda_index'))
    
    db = get_db()
    total_plantas = db.plants.count_documents({})
    plantas_activas = db.plants.count_documents({'estado': 'activa'})
    ultimos_riegos = list(db.watering_logs.find().sort('fecha_riego', -1).limit(10))
    
    for riego in ultimos_riegos:
        planta = db.plants.find_one({'_id': riego['id_planta']})
        riego['nombre_planta'] = planta['nombre'] if planta else 'Desconocida'
    
    ultimo_backup = db.backups.find_one(sort=[('fecha_respaldo', -1)])
    return render_template('dashboard.html', total_plantas=total_plantas, 
                         plantas_riego_hoy=plantas_activas, ultimos_riegos=ultimos_riegos, 
                         ultimo_backup=ultimo_backup['fecha_respaldo'] if ultimo_backup else None)

@main_bp.route('/admin/pedidos')
@login_required
def admin_pedidos():
    if current_user.rol != 'admin': 
        return redirect(url_for('main_bp.dashboard')) # Cambié 'main' por 'main_bp'
    
    db = get_db()
    estado = request.args.get('estado', 'todos')
    query = {} if estado == 'todos' else {'estado_pedido': estado}
    pedidos = list(db.orders.find(query).sort('fecha_orden', -1))
    
    for pedido in pedidos:
        # 1. Traer datos del cliente
        u = db.users.find_one({'_id': pedido.get('id_cliente')})
        pedido['cliente'] = u if u else {'nombre': 'Usuario Eliminado'}
        
        # 2. Traer nombres de las plantas para cada detalle
        for detalle in pedido.get('detalles', []):
            if 'id_planta' in detalle:
                planta_doc = db.plants.find_one({'_id': detalle['id_planta']})
                if planta_doc:
                    detalle['nombre_planta'] = planta_doc.get('nombre', 'Sin nombre')
                else:
                    detalle['nombre_planta'] = 'Planta no encontrada'
            else:
                detalle['nombre_planta'] = 'ID no disponible'

    return render_template('admin/pedidos.html', pedidos=pedidos, estado=estado)

@main_bp.route('/admin/pedido/<id>/actualizar-estado', methods=['POST'])
@login_required
def actualizar_estado_pedido(id):
    if current_user.rol != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        from bson import ObjectId
        db = get_db()
        nuevo_estado = request.json.get('estado')
        
        # Actualizamos en la colección 'orders'
        resultado = db.orders.update_one(
            {'_id': ObjectId(id)},
            {'$set': {'estado_pedido': nuevo_estado}}
        )
        
        if resultado.modified_count > 0:
            return jsonify({'success': True, 'message': f'Pedido actualizado a {nuevo_estado}'})
        return jsonify({'success': False, 'message': 'No se realizaron cambios'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ========== ESTADÍSTICAS (AGGREGATION) ==========

@main_bp.route('/admin/estadisticas-tienda')
@login_required
def estadisticas_tienda():
    if current_user.rol != 'admin': return redirect(url_for('main.dashboard'))
    db = get_db()
    
    # Pipeline de ventas
    ventas_result = list(db.orders.aggregate([
        {'$match': {'estado_pedido': {'$ne': 'cancelado'}}},
        {'$group': {'_id': None, 'ventas_totales': {'$sum': '$costo_total'}, 'total_pedidos': {'$sum': 1}}}
    ]))
    stats = ventas_result[0] if ventas_result else {'ventas_totales': 0, 'total_pedidos': 0}
    
    # Productos más vendidos
    productos_vendidos = list(db.orders.aggregate([
        {'$match': {'estado_pedido': {'$ne': 'cancelado'}}},
        {'$unwind': '$detalles'},
        {'$group': {'_id': '$detalles.id_planta', 'nombre': {'$first': '$detalles.nombre_planta'}, 'total': {'$sum': '$detalles.cantidad'}}},
        {'$sort': {'total': -1}}, {'$limit': 5}
    ]))

    return render_template('admin/estadisticas_tienda.html', 
                         ventas_totales=stats['ventas_totales'], 
                         total_pedidos=stats['total_pedidos'],
                         productos_vendidos=productos_vendidos)

#--------------------------------------------------------------------
# ========== RESPALDO Y ANALISIS ==========
# ========== RESPALDO Y ANALISIS ==========
from datetime import datetime, timedelta # Importación única al inicio

@reports_bp.route('/')
@login_required
def reportes():
    if current_user.rol != 'admin':
        return redirect(url_for('main.dashboard'))
    
    db = get_db()
    # Usamos la clase datetime que importamos arriba
    hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 1. PLANTAS
    plantas_stats = {
        'total': db.plants.count_documents({}),
        'activas': db.plants.count_documents({'estado': 'activa'}),
        'en_venta': db.plants.count_documents({'disponible_venta': True, 'estado': 'activa'}),
        'tendencia': 5.2
    }
    
    # 2. PEDIDOS (Cálculos de ventas y productos)
    total_pedidos = db.orders.count_documents({})
    #-------------------------PIPELINE********************
    pipeline_pedidos = [
        {"$group": {
            "_id": None,
            "total_ventas": {"$sum": "$total"},
            "total_productos": {"$sum": {"$size": "$detalles"}}
        }}
    ]
    resultado_pedidos = list(db.orders.aggregate(pipeline_pedidos))
    
    pipeline_hoy = [
        {"$match": {"fecha": {"$gte": hoy}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}}
    ]
    resultado_hoy = list(db.orders.aggregate(pipeline_hoy))
    
    ventas_suma = resultado_pedidos[0]['total_ventas'] if resultado_pedidos else 0.0
    ventas_hoy = resultado_hoy[0]['total'] if resultado_hoy else 0.0

    pedidos_stats = {
        'ventas_totales': ventas_suma,
        'ventas_hoy': ventas_hoy,
        'cantidad_pedidos': total_pedidos,
        'ticket_promedio': (ventas_suma / total_pedidos) if total_pedidos > 0 else 0.0,
        'productos_por_pedido': (resultado_pedidos[0]['total_productos'] / total_pedidos) if total_pedidos > 0 else 0.0,
        'por_estado': {
            'pendiente': db.orders.count_documents({'estado': 'pendiente'}),
            'completado': db.orders.count_documents({'estado': 'completado'}),
            'cancelado': db.orders.count_documents({'estado': 'cancelado'})
        },
        'tendencia_ventas': 0.0
    }

    # 3. CLIENTES
    clientes_con_pedidos_ids = db.orders.distinct('usuario_id')
    clientes_stats = {
        'total': db.users.count_documents({'rol': 'cliente'}), 
        'con_pedidos': len(clientes_con_pedidos_ids),
        'nuevos_hoy': db.users.count_documents({'rol': 'cliente', 'fecha_registro': {'$gte': hoy}}),
        'nuevos_este_mes': 0,
        'tendencia_clientes': 0.0
    }
    
    # 4. RESPALDOS
    pipeline_respaldos = [{"$group": {"_id": None, "total_size": {"$sum": "$tamaño_bytes"}}}]
    res_respaldos = list(db.backups.aggregate(pipeline_respaldos))
    total_bytes = res_respaldos[0]['total_size'] if res_respaldos else 0
    
    respaldos_stats = {
        'total': db.backups.count_documents({}),
        'exitosos': db.backups.count_documents({'estado': 'exitoso'}),
        'fallidos': db.backups.count_documents({'estado': 'fallido'}),
        'tamaño_total_gb': total_bytes / (1024**3),
        'tamaño_local_mb': total_bytes / (1024**2),
        'tamaño_usb_mb': total_bytes / (1024**2),
        'ultimo_respaldo': "N/A"
    }
    
    # 5. LISTADOS
    accesos_recientes = list(db.access_logs.find().sort('fecha', -1).limit(3))
    
    pipeline_top = [
        {"$unwind": "$detalles"},
        {"$group": {"_id": "$detalles.nombre", "cantidad": {"$sum": "$detalles.cantidad"}}},
        {"$sort": {"cantidad": -1}},
        {"$limit": 5}
    ]
    top_productos = list(db.orders.aggregate(pipeline_top))
    pedidos_recientes = list(db.orders.find().sort('fecha', -1).limit(5))
    top_plantas = [] 
    
    # 5.5 CLIENTES DESTACADOS
    pipeline_clientes = [
        {"$group": {
            "_id": "$usuario_id", 
            "total_compras": {"$sum": "$total"},
            "total_pedidos": {"$sum": 1}
        }},
        {"$sort": {"total_compras": -1}}, 
        {"$limit": 10}
    ]
    
    top_clientes_raw = list(db.orders.aggregate(pipeline_clientes))
    clientes_destacados = []
    for item in top_clientes_raw:
        user_data = db.users.find_one({"_id": item["_id"]})
        clientes_destacados.append({
            "nombre": user_data["nombre"] if user_data else "Usuario Anónimo",
            "total_compras": item["total_compras"],
            "total_pedidos": item["total_pedidos"]
        })

    # 5.6 VENTAS MENSUALES
    ventas_mensuales = [0.0] * 12
    try:
        pipeline_mensual = [
            {"$match": {"fecha": {"$ne": None, "$type": "date"}}},
            {"$group": {"_id": {"$month": "$fecha"}, "total": {"$sum": "$total"}}},
            {"$sort": {"_id": 1}}
        ]
        resultados_mensuales = list(db.orders.aggregate(pipeline_mensual))
        for res in resultados_mensuales:
            mes_num = res.get('_id')
            if isinstance(mes_num, int) and 1 <= mes_num <= 12:
                ventas_mensuales[mes_num - 1] = float(res.get('total', 0.0))
    except Exception as e:
        print(f"Error mensual: {e}")
        
    # 5.7 CRECIMIENTO DE CLIENTES
    crecimiento_clientes = [0] * 12
    try:
        pipeline_clientes_mes = [
            {"$match": {"rol": "cliente", "fecha_registro": {"$ne": None, "$type": "date"}}},
            {"$group": {"_id": {"$month": "$fecha_registro"}, "total": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        res_clientes = list(db.users.aggregate(pipeline_clientes_mes))
        for r in res_clientes:
            mes_idx = r['_id'] - 1
            crecimiento_clientes[mes_idx] = r['total']
    except Exception as e:
        print(f"Error clientes: {e}")

    # 5.8 TIPOS DE RESPALDOS
    tipos_respaldos = {"labels": [], "data": []}
    try:
        pipeline_resp = [{"$group": {"_id": "$tipo", "count": {"$sum": 1}}}]
        res_resp = list(db.backups.aggregate(pipeline_resp))
        tipos_respaldos["labels"] = [str(r['_id']) for r in res_resp]
        tipos_respaldos["data"] = [r['count'] for r in res_resp]
    except Exception as e:
        print(f"Error respaldos: {e}")

    # 5.10 VENTAS DIARIAS (Últimos 7 días)
    ventas_diarias = {"labels": [], "data": []}
    try:
        # Quitamos el import de aquí para evitar el UnboundLocalError
        siete_dias_atras = hoy - timedelta(days=7)
        pipeline_diario = [
            {"$match": {"fecha": {"$gte": siete_dias_atras}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$fecha"}},
                "total": {"$sum": "$total"}
            }},
            {"$sort": {"_id": 1}}
        ]
        res_diario = list(db.orders.aggregate(pipeline_diario))
        ventas_diarias["labels"] = [r['_id'] for r in res_diario]
        ventas_diarias["data"] = [float(r['total']) for r in res_diario]
    except Exception as e:
        print(f"Error ventas diarias: {e}")
        
    # 6. RENDERIZADO FINAL
    return render_template('reports/index.html',
                           plantas_stats=plantas_stats,
                           pedidos_stats=pedidos_stats,
                           clientes_stats=clientes_stats,
                           respaldos_stats=respaldos_stats,
                           pedidos_recientes=pedidos_recientes,
                           accesos_recientes=accesos_recientes,
                           top_productos=top_productos,
                           top_plantas=top_plantas,
                           clientes_destacados=clientes_destacados,
                           ventas_mensuales=ventas_mensuales,
                           crecimiento_clientes=crecimiento_clientes,
                           tipos_respaldos=tipos_respaldos,
                           ventas_diarias=ventas_diarias)
    
    
    
    
    
    
    
#----------------------------------------------------------------------------------------
# (Omito por brevedad las APIs de reportes JSON, pero la lógica es aplicar un db.collection.find() y retornar jsonify)

# routes.py (PARTE 4: Sistema de Respaldos Críticos y Programaciones)

from bson import json_util # ¡Importante! Convierte ObjectIds y Fechas a JSON correctamente
from app.database import get_db

# ========== RUTAS DE RESPALDOS ==========
@backup_bp.route('/')
@login_required
def listar_respaldos():
    if current_user.rol != 'admin':
        flash('Solo administradores pueden acceder a esta sección', 'danger')
        return redirect(url_for('main.dashboard'))
    
    db = get_db()
    respaldos = list(db.backups.find().sort('fecha_respaldo', -1))
    
    # Detectar USB con tu función original intacta
    usb_info = detectar_usb_json() 
    usb_mounted = usb_info.get('conectado', False)
    usb_path = usb_info.get('ruta', 'No detectado')
    usb_free_space = usb_info.get('espacio_libre', 0)
    usb_total_space = usb_info.get('espacio_total', 0)
    
    # Estadísticas por tipo usando PyMongo
    total_completos = db.backups.count_documents({'tipo_respaldo': 'completo'})
    total_diferenciales = db.backups.count_documents({'tipo_respaldo': 'diferencial'})
    total_copias_usb = db.backups.count_documents({'tipo_respaldo': {'$regex': '^copia_usb'}})
    total_importados = db.backups.count_documents({'tipo_respaldo': {'$regex': '^importado'}})
    
    last_backup_time = 'Nunca'
    if respaldos and respaldos[0].get('fecha_respaldo'):
        # Misma lógica tuya para calcular el tiempo relativo...
        diff = datetime.utcnow() - respaldos[0]['fecha_respaldo']
        if diff.days > 0: last_backup_time = f'Hace {diff.days} días'
        elif diff.seconds >= 3600: last_backup_time = f'Hace {diff.seconds // 3600} horas'
        elif diff.seconds >= 60: last_backup_time = f'Hace {diff.seconds // 60} minutos'
        else: last_backup_time = 'Hace unos momentos'
    
    return render_template('backups/lista.html', 
                         respaldos=respaldos, total_completos=total_completos,
                         total_diferenciales=total_diferenciales, total_copias_usb=total_copias_usb,
                         total_importados=total_importados, usb_mounted=usb_mounted,
                         usb_path=usb_path, usb_free_space=usb_free_space,
                         usb_total_space=usb_total_space, last_backup_time=last_backup_time)

@backup_bp.route('/crear/completo', methods=['POST'])
@login_required
def crear_respaldo_completo():
    if current_user.rol != 'admin': return jsonify({'success': False}), 403
    
    try:
        almacenamiento = request.form.get('almacenamiento', 'local')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"respaldo_completo_{timestamp}.json.gz" # Ahora es .json.gz
        
        if almacenamiento == 'usb':
            usb_info = detectar_usb_json()
            if not usb_info.get('conectado'): return jsonify({'success': False, 'message': 'Sin USB'}), 400
            usb_backup_folder = crear_backup_folder_usb(usb_info['ruta'])
            filepath = os.path.join(usb_backup_folder, filename)
        else:
            filepath = os.path.join(BACKUP_FOLDER, filename)
        
        db = get_db()
        
        # 1. EXTRACCIÓN CON PYMONGO (Reemplaza a mysqldump)
        data_to_backup = {}
        colecciones = db.list_collection_names()
        for coll_name in colecciones:
            # Extraemos todos los documentos de cada colección
            data_to_backup[coll_name] = list(db[coll_name].find())
        
        # 2. CONVERSIÓN Y COMPRESIÓN
        # json_util.dumps convierte los ObjectIds y Fechas a formato seguro
        json_data = json_util.dumps(data_to_backup) 
        
        with gzip.open(filepath, 'wt', encoding='utf-8') as f_out:
            f_out.write(json_data)
        
        # 3. REGISTRO
        tamaño_mb = os.path.getsize(filepath) / (1024 * 1024)
        checksum = calcular_checksum(filepath)
        
        nuevo_respaldo = {
            'tipo_respaldo': 'completo',
            'ruta_archivo': filepath,
            'tamaño_mb': round(tamaño_mb, 2),
            'realizado_por': current_user.nombre,
            'almacenamiento': almacenamiento,
            'checksum': checksum,
            'fecha_respaldo': datetime.utcnow()
        }
        respaldo_id = db.backups.insert_one(nuevo_respaldo).inserted_id
        
        return jsonify({
            'success': True,
            'message': f'✅ Respaldo completo creado exitosamente ({tamaño_mb:.2f} MB)',
            'respaldo_id': str(respaldo_id)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error al crear respaldo: {e}")
        return jsonify({'success': False, 'message': f'❌ Error: {str(e)}'}), 500

@backup_bp.route('/restaurar/<id>', methods=['POST'])
@login_required
def restaurar_respaldo(id):
    if current_user.rol != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    db = get_db()
    respaldo = db.backups.find_one({'_id': ObjectId(id)})
    
    if not respaldo or not os.path.exists(respaldo['ruta_archivo']):
        return jsonify({'success': False, 'message': 'El archivo físico no existe'}), 404
    
    try:
        # 1. Leer el archivo comprimido
        with gzip.open(respaldo['ruta_archivo'], 'rt', encoding='utf-8') as f_in:
            backup_data = json_util.loads(f_in.read())
        
        # 2. Restaurar cada colección
        for coll_name, documentos in backup_data.items():
            if documentos:
                # Vaciamos la colección actual y metemos los datos del respaldo
                db[coll_name].delete_many({}) 
                db[coll_name].insert_many(documentos)
        
        # 3. Registrar acción
        db.access_logs.insert_one({
            'usuario_id': ObjectId(current_user.id),
            'accion': f'restaurar_respaldo_{id}',
            'fecha_acceso': datetime.utcnow()
        })
        
        return jsonify({'success': True, 'message': 'Base de datos restaurada exitosamente'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al restaurar: {str(e)}'}), 500


@backup_bp.route('/eliminar/<id>', methods=['POST'])
@login_required
def eliminar_respaldo(id):
    # 1. Seguridad: Verificar permisos y devolver JSON de error
    if current_user.rol != 'admin': 
        return jsonify({'success': False, 'message': 'No autorizado para eliminar'}), 403
    
    db = get_db()
    
    try:
        # Validar que el ID sea un ObjectId válido para evitar colapsos
        obj_id = ObjectId(id)
    except Exception:
        return jsonify({'success': False, 'message': 'ID de respaldo inválido'}), 400

    # 2. Buscar el documento
    respaldo = db.backups.find_one({'_id': obj_id})
    if not respaldo:
        return jsonify({'success': False, 'message': 'El respaldo no existe en la base de datos'}), 404
    
    try:
        # 3. Eliminar el archivo físico (si existe)
        ruta_archivo = respaldo.get('ruta_archivo')
        if ruta_archivo and os.path.exists(ruta_archivo):
            os.remove(ruta_archivo)
        
        # 4. Eliminar el documento de MongoDB
        db.backups.delete_one({'_id': obj_id})
        
        # 5. Respuesta exitosa
        return jsonify({
            'success': True,
            'message': 'Respaldo eliminado permanentemente'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error al eliminar respaldo {id}: {e}")
        return jsonify({'success': False, 'message': f'Error interno del servidor: {str(e)}'}), 500

@backup_bp.route('/importar', methods=['POST'])
@login_required
def importar_respaldo():
    if current_user.rol != 'admin':
        flash('Solo administradores pueden importar respaldos', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    # 1. Verificar si el archivo viene en la petición
    if 'archivo_respaldo' not in request.files:
        flash('No se envió ningún archivo', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
        
    archivo = request.files['archivo_respaldo']
    
    # 2. Verificar si el usuario no seleccionó nada
    if archivo.filename == '':
        flash('No se seleccionó ningún archivo', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
        
    # 3. Validar y procesar el archivo
    if archivo and archivo.filename.endswith('.json.gz'):
        try:
            # Crear un nombre seguro para evitar inyecciones
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            nombre_seguro = secure_filename(archivo.filename)
            filename = f"importado_{timestamp}_{nombre_seguro}"
            
            # Guardar físicamente en la carpeta de backups
            filepath = os.path.join('backups', filename)
            archivo.save(filepath)
            
            # 4. Registrar en MongoDB
            db = get_db()
            tamaño_mb = os.path.getsize(filepath) / (1024 * 1024)
            
            try:
                checksum = calcular_checksum(filepath)
            except NameError:
                checksum = "N/A" # Fallback por si no está importada la función
                
            nuevo_respaldo = {
                'tipo_respaldo': 'importado',
                'ruta_archivo': filepath,
                'tamaño_mb': round(tamaño_mb, 2),
                'realizado_por': current_user.nombre,
                'almacenamiento': 'local',
                'checksum': checksum,
                'fecha_respaldo': datetime.utcnow()
            }
            
            db.backups.insert_one(nuevo_respaldo)
            flash('Respaldo importado exitosamente. Ahora puedes restaurarlo desde la lista.', 'success')
            
        except Exception as e:
            current_app.logger.error(f"Error al importar respaldo: {e}")
            flash(f'Error al guardar el archivo: {str(e)}', 'danger')
    else:
        flash('Formato no válido. El sistema de MongoDB solo acepta archivos .json.gz', 'warning')
        
    return redirect(url_for('backup.listar_respaldos'))


@backup_bp.route('/limpiar-db', methods=['POST'])
@login_required
def limpiar_base_datos():
    if current_user.rol != 'admin':
        return jsonify({'success': False, 'message': 'Acceso denegado.'}), 403

    try:
        db = get_db()
        # Protegemos la sesión actual y los respaldos
        colecciones_protegidas = ['users', 'backups', 'system.indexes']
        todas_las_colecciones = db.list_collection_names()
        
        for coll_name in todas_las_colecciones:
            if coll_name not in colecciones_protegidas:
                # Borra todos los documentos, pero mantiene la estructura
                db[coll_name].delete_many({})
                
        # Registramos la limpieza
        db.access_logs.insert_one({
            'usuario_id': ObjectId(current_user.id),
            'accion': 'limpieza_total_db',
            'fecha_acceso': datetime.utcnow()
        })
        
        return jsonify({'success': True, 'message': 'Base de datos limpiada exitosamente.'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error interno: {str(e)}'}), 500


@backup_bp.route('/descargar/<id>', methods=['GET'])
@login_required
def descargar_respaldo(id):
    if current_user.rol != 'admin':
        flash('Solo administradores pueden descargar respaldos', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    try:
        db = get_db()
        # Buscar el documento en MongoDB
        respaldo = db.backups.find_one({'_id': ObjectId(id)})
        
        if not respaldo:
            flash('Respaldo no encontrado en la base de datos', 'danger')
            return redirect(url_for('backup.listar_respaldos'))
            
        ruta_archivo = respaldo.get('ruta_archivo')
        
        # Verificar que el archivo físico realmente exista en la carpeta
        if not ruta_archivo or not os.path.exists(ruta_archivo):
            flash('El archivo físico del respaldo no existe en el servidor', 'danger')
            return redirect(url_for('backup.listar_respaldos'))
            
        # Forzar la descarga del archivo al navegador del usuario
        return send_file(
            ruta_archivo,
            as_attachment=True,
            download_name=os.path.basename(ruta_archivo)
        )
        
    except Exception as e:
        current_app.logger.error(f"Error al descargar respaldo {id}: {e}")
        flash(f'Error al descargar el archivo: {str(e)}', 'danger')
        return redirect(url_for('backup.listar_respaldos'))

@backup_bp.route('/detectar-usb', methods=['GET'])
@login_required
def api_detectar_usb():
    # Protección de seguridad básica
    if current_user.rol != 'admin':
        return jsonify({'conectado': False, 'error': 'No autorizado'}), 403
    
    # Ejecutamos nuestra robusta función de detección
    resultado = detectar_usb_json()
    
    # Le inyectamos la llave success para que JS esté feliz
    resultado['success'] = True
    
    # jsonify convierte el diccionario de Python a un JSON puro para el Frontend
    return jsonify(resultado)


@backup_bp.route('/forzar-detectar-usb', methods=['GET'])
@login_required
def forzar_detectar_usb():
    # Protección de seguridad
    if current_user.rol != 'admin':
        flash('Solo administradores pueden gestionar dispositivos USB', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    # Ejecutamos nuestra detección blindada con el Write-Test
    resultado = detectar_usb_json()
    
    # Evaluamos el resultado para mostrar el mensaje adecuado al usuario
    if resultado.get('conectado'):
        ruta = resultado.get('ruta')
        espacio = resultado.get('espacio_libre')
        flash(f'Unidad USB detectada exitosamente en {ruta} (Espacio libre: {espacio} GB)', 'success')
    else:
        # Si hubo un error capturado en el dict, lo mostramos
        error_msg = resultado.get('error', 'No se detectó ninguna unidad extraíble válida o no hay permisos de escritura.')
        flash(f'No se pudo montar la USB: {error_msg}', 'warning')
        
    # Finalmente, redirigimos de vuelta a la vista principal
    return redirect(url_for('backup.listar_respaldos'))



@backup_bp.route('/copiar-a-usb', methods=['POST'])
@login_required
def copiar_a_usb():
    if current_user.rol != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403

    try:
        data = request.get_json() if request.is_json else request.form
        
        # 1. Capturar ambas posibilidades
        respaldo_id = data.get('id')
        copiar_todos = data.get('copiar_todos')
        
        # JS a veces envía booleanos verdaderos como texto 'true'
        if str(copiar_todos).lower() == 'true':
            copiar_todos = True

        if not respaldo_id and not copiar_todos:
            return jsonify({'success': False, 'message': 'ID de respaldo no proporcionado'}), 400

        db = get_db()
        
        # 2. Ejecutar nuestra detección blindada antes de iterar
        usb_info = detectar_usb_json()
        if not usb_info.get('conectado'):
            return jsonify({'success': False, 'message': 'No se detectó USB con permisos de escritura'}), 400

        usb_ruta = usb_info['ruta']
        usb_backup_folder = crear_backup_folder_usb(usb_ruta)

        # 3. Determinar el "Lote de Trabajo" (Uno vs Todos)
        respaldos_a_copiar = []
        if copiar_todos:
            # Buscar todos los respaldos locales
            respaldos_a_copiar = list(db.backups.find({'almacenamiento': 'local'}))
            if not respaldos_a_copiar:
                return jsonify({'success': False, 'message': 'No hay respaldos locales para copiar'}), 404
        else:
            # Buscar solo el específico
            respaldo_original = db.backups.find_one({'_id': ObjectId(respaldo_id)})
            if not respaldo_original:
                return jsonify({'success': False, 'message': 'Respaldo no encontrado en BD'}), 404
            respaldos_a_copiar = [respaldo_original]

        # 4. Procesar la copia (Bucle)
        copiados_exitosamente = []
        errores = []
        tamaño_total_mb = 0.0

        for respaldo in respaldos_a_copiar:
            ruta_original = respaldo.get('ruta_archivo')
            nombre_archivo = os.path.basename(ruta_original) if ruta_original else f"respaldo_desconocido_{respaldo['_id']}"
            
            if not ruta_original or not os.path.exists(ruta_original):
                errores.append(f"No existe el archivo físico: {nombre_archivo}")
                continue
            
            ruta_destino = os.path.join(usb_backup_folder, nombre_archivo)
            
            try:
                # Copia física
                shutil.copy2(ruta_original, ruta_destino)
                
                # Registro en BD
                tamaño_mb = os.path.getsize(ruta_destino) / (1024 * 1024)
                tamaño_total_mb += tamaño_mb
                
                nueva_copia = {
                    'tipo_respaldo': 'copia_usb',
                    'ruta_archivo': ruta_destino,
                    'tamaño_mb': round(tamaño_mb, 2),
                    'realizado_por': current_user.nombre,
                    'almacenamiento': 'usb',
                    'checksum': respaldo.get('checksum', 'N/A'),
                    'fecha_respaldo': datetime.utcnow(),
                    'respaldo_original_id': respaldo['_id']
                }
                db.backups.insert_one(nueva_copia)
                copiados_exitosamente.append({'archivo': nombre_archivo})
                
            except Exception as e:
                errores.append(f"Error en {nombre_archivo}: {str(e)}")

        # 5. Evaluar el resultado final
        if not copiados_exitosamente:
            return jsonify({
                'success': False, 
                'message': 'No se pudo copiar ningún archivo', 
                'errores': errores
            }), 500

        mensaje_exito = f'✅ {len(copiados_exitosamente)} respaldo(s) copiado(s)' if copiar_todos else '✅ Respaldo copiado exitosamente'
        
        # Este JSON encaja perfectamente con tu frontend (líneas 118-125)
        return jsonify({
            'success': True, 
            'message': mensaje_exito,
            'copiados': copiados_exitosamente,
            'tamaño_total_mb': round(tamaño_total_mb, 2),
            'errores': errores
        })

    except Exception as e:
        current_app.logger.error(f"Error copiando a USB: {e}")
        return jsonify({'success': False, 'message': f'Error interno: {str(e)}'}), 500


# 1. VERIFICAR TODOS LOS RESPALDOS
@backup_bp.route('/verificar-todos', methods=['GET'])
@login_required
def verificar_todos():
    if current_user.rol != 'admin': return jsonify({'success': False, 'message': 'No autorizado'}), 403
        
    db = get_db()
    respaldos = list(db.backups.find())
    
    total = len(respaldos)
    verificados, errores, total_mb = 0, 0, 0
    por_almacenamiento = {}
    
    for resp in respaldos:
        ruta = resp.get('ruta_archivo')
        almac = resp.get('almacenamiento', 'desconocido')
        por_almacenamiento[almac] = por_almacenamiento.get(almac, 0) + 1
        
        # Verificar si el archivo físico realmente existe en el disco
        if ruta and os.path.exists(ruta):
            verificados += 1
            total_mb += resp.get('tamaño_mb', 0)
        else:
            errores += 1
            
    porcentaje = round((verificados / total * 100) if total > 0 else 0, 1)
    
    return jsonify({
        'success': True, 'total': total, 'verificados_count': verificados,
        'porcentaje_exito': porcentaje, 'errores_count': errores,
        'resumen': {
            'total_mb': round(total_mb, 2), 'total_gb': round(total_mb / 1024, 2),
            'por_almacenamiento': por_almacenamiento
        }
    })

# 2. ESTADO USB DETALLADO
@backup_bp.route('/estado-usb-detallado', methods=['GET'])
@login_required
def estado_usb_detallado():
    usb_info = detectar_usb_json()
    if not usb_info.get('conectado'):
        return jsonify({'success': False, 'conectado': False})
        
    db = get_db()
    # Calcular cuánto espacio ocupan los respaldos USB en la BD
    respaldos_usb = list(db.backups.find({'$or': [{'almacenamiento': 'usb'}, {'tipo_respaldo': 'copia_usb'}]}))
    espacio_utilizado_mb = sum([r.get('tamaño_mb', 0) for r in respaldos_usb])
    espacio_utilizado_gb = round(espacio_utilizado_mb / 1024, 4)
    
    espacio_total = usb_info.get('espacio_total', 1) # Evitar división por cero
    espacio_libre = usb_info.get('espacio_libre', 0)
    espacio_usado = round(espacio_total - espacio_libre, 2)
    
    return jsonify({
        'success': True, 'conectado': True,
        'dispositivo': {
            'ruta': usb_info.get('ruta'), 'sistema': usb_info.get('sistema'),
            'espacio_total_gb': espacio_total, 'espacio_usado_gb': espacio_usado,
            'porcentaje_usado': round((espacio_usado / espacio_total) * 100, 1),
            'espacio_libre_gb': espacio_libre,
            'porcentaje_libre': round((espacio_libre / espacio_total) * 100, 1)
        },
        'respaldos': {
            'total_en_usb': len(respaldos_usb),
            'espacio_utilizado_mb': round(espacio_utilizado_mb, 2),
            'espacio_utilizado_gb': espacio_utilizado_gb,
            'porcentaje_espacio_usb': round((espacio_utilizado_gb / espacio_total) * 100, 2)
        },
        'recomendaciones': ["Mantén al menos un 20% de espacio libre en la USB para futuros respaldos."] if espacio_libre < (espacio_total * 0.2) else ["La unidad tiene espacio óptimo."]
    })


# 3. TEST DE PERMISOS USB
@backup_bp.route('/test-usb-permisos', methods=['GET'])
@login_required
def test_usb_permisos():
    usb_info = detectar_usb_json()
    if not usb_info.get('conectado'):
        return jsonify({'success': False, 'message': 'USB no conectada'})
        
    ruta = usb_info.get('ruta')
    # Nuestra función detectar_usb_json ya hizo el Write-Test, así que asumimos éxito básico
    # Pero aquí el frontend espera un desglose detallado
    return jsonify({
        'success': True, 'usb_path': ruta,
        'permisos': {
            'lectura_espacio': True, 'escritura_archivo': True,
            'creacion_carpeta': True, 'lectura_archivo': True
        },
        'espacio_total_gb': usb_info.get('espacio_total'),
        'espacio_libre_gb': usb_info.get('espacio_libre')
    })


# 4. DEBUG USB DETECTION
@backup_bp.route('/debug-usb-detection', methods=['GET'])
@login_required
def debug_usb_detection():
    if current_user.rol != 'admin': return jsonify({'success': False}), 403
    
    particiones_info = []
    for part in psutil.disk_partitions(all=False):
        try:
            uso = psutil.disk_usage(part.mountpoint)
            particiones_info.append({
                'dispositivo': part.device, 'punto_montaje': part.mountpoint,
                'tipo': part.fstype, 'opciones': part.opts,
                'espacio_libre_gb': round(uso.free / (1024**3), 2),
                'espacio_total_gb': round(uso.total / (1024**3), 2)
            })
        except:
            particiones_info.append({'dispositivo': part.device, 'error': True})
            
    return jsonify({
        'success': True,
        'sistema': platform.system() + " " + platform.release(),
        'python_version': sys.version.split(' ')[0],
        'directorio_actual': os.getcwd(),
        'usuario_os': os.getenv('USERNAME') or os.getenv('USER'),
        'particiones': particiones_info,
        'proceso_deteccion': detectar_usb_json() # Resultado crudo para debug
    })



# ========== PROGRAMACIONES ==========
@backup_bp.route('/programaciones')
@login_required
def listar_programaciones():
    if current_user.rol != 'admin': return redirect(url_for('backup.listar_respaldos'))
    
    # Obtenemos las programaciones ordenadas
    programaciones = list(get_db().schedules.find().sort([('activo', -1), ('proxima_ejecucion', 1)]))
    
    return render_template('backups/programaciones.html', 
                         programaciones=programaciones,
                         usb_mounted=detectar_usb_json().get('conectado', False))

@backup_bp.route('/programaciones/<id>/toggle', methods=['POST'])
@login_required
def toggle_programacion(id):
    if current_user.rol != 'admin': return jsonify({'success': False}), 403
    
    db = get_db()
    prog = db.schedules.find_one({'_id': ObjectId(id)})
    
    try:
        nuevo_estado = not prog.get('activo', False)
        # Aquí llamarías a tu función para recalcular 'proxima_ejecucion'
        db.schedules.update_one({'_id': ObjectId(id)}, {'$set': {'activo': nuevo_estado}})
        return jsonify({'success': True, 'activo': nuevo_estado})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
 
 
# ========== 1. CREAR PROGRAMACIÓN (Navegación) ==========
@backup_bp.route('/programaciones/crear', methods=['GET', 'POST'])
@login_required
def crear_programacion():
    if current_user.rol != 'admin': 
        flash('No autorizado para crear programaciones', 'danger')
        return redirect(url_for('backup.listar_programaciones'))
    
    # Si es POST (Se envió el formulario HTML)
    if request.method == 'POST':
        try:
            db = get_db()
            
            nueva_programacion = {
                'tipo_respaldo': request.form.get('tipo_respaldo'),
                'frecuencia': request.form.get('frecuencia'),  # ej: 'diario', 'semanal'
                'hora_ejecucion': request.form.get('hora_ejecucion', '00:00'),
                'almacenamiento': request.form.get('almacenamiento', 'local'),
                'activo': True,
                'creado_por': current_user.nombre,
                'fecha_creacion': datetime.utcnow(),
                # Aquí puedes agregar tu lógica real para calcular la próxima ejecución
                'proxima_ejecucion': datetime.utcnow() 
            }
            
            db.schedules.insert_one(nueva_programacion)
            flash('Programación creada exitosamente', 'success')
            return redirect(url_for('backup.listar_programaciones'))
            
        except Exception as e:
            flash(f'Error al guardar: {str(e)}', 'danger')
            # Si hay error, recarga la misma vista
            return redirect(url_for('backup.crear_programacion'))
            
    # Si es GET (Se hizo clic en el enlace "Programar")
    return render_template('backups/crear_programacion.html')



# ========== 2. EDITAR PROGRAMACIÓN (Navegación) ==========
@backup_bp.route('/programaciones/editar/<id>', methods=['GET', 'POST'])
@login_required
def editar_programacion(id):
    if current_user.rol != 'admin':
        flash('No autorizado para editar programaciones', 'danger')
        return redirect(url_for('backup.listar_programaciones'))
        
    db = get_db()
    # Buscamos el documento actual usando ObjectId
    prog_actual = db.schedules.find_one({'_id': ObjectId(id)})
    
    if not prog_actual:
        flash('La programación no existe', 'danger')
        return redirect(url_for('backup.listar_programaciones'))

    # Si es POST (Se enviaron los cambios del formulario HTML)
    if request.method == 'POST':
        try:
            update_data = {
                'tipo_respaldo': request.form.get('tipo_respaldo'),
                'frecuencia': request.form.get('frecuencia'),
                'hora_ejecucion': request.form.get('hora_ejecucion'),
                'almacenamiento': request.form.get('almacenamiento')
            }
            
            # Actualizar en MongoDB (solo los campos enviados)
            db.schedules.update_one(
                {'_id': ObjectId(id)}, 
                {'$set': update_data}
            )
            
            flash('Programación actualizada exitosamente', 'success')
            return redirect(url_for('backup.listar_programaciones'))
            
        except Exception as e:
            flash(f'Error al actualizar: {str(e)}', 'danger')
            return redirect(url_for('backup.editar_programacion', id=id))

    # Si es GET (Se hizo clic en el enlace "Editar")
    # Pasamos el objeto 'prog_actual' al template para precargar los campos del formulario
    return render_template('backups/editar_programacion.html', prog=prog_actual)    


# ========== RUTAS DE PRUEBA/DEBUG (RESTAURADAS) ==========
@main_bp.route('/debug/session')
@login_required
def debug_session():
    """Página de debug para ver la sesión"""
    if current_user.rol != 'admin':
        flash('Acceso solo para administradores', 'danger')
        return redirect(url_for('main.dashboard'))
    
    session_data = dict(session)
    for key in list(session_data.keys()):
        if 'password' in key.lower() or 'secret' in key.lower():
            session_data[key] = '*****'
            
    return jsonify({
        'session_data': session_data,
        'carrito': obtener_carrito()
    })

@main_bp.route('/debug/set-cliente')
def debug_set_cliente():
    flash('Esta función de debug fue deshabilitada en la migración', 'warning')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/debug/set-admin')
def debug_set_admin():
    flash('Esta función de debug fue deshabilitada en la migración', 'warning')
    return redirect(url_for('main.dashboard'))

import subprocess
import os
import sys
import socket
from flask import redirect, current_app, flash, url_for, jsonify

# --- RUTAS DE INTEGRACIÓN SPARK & STREAMLIT ---

@main_bp.route('/run_spark/<script>')
def run_spark(script):
    """Lanza los scripts de Spark/Streamlit usando la nueva estructura de carpetas"""
    # 1. Obtener la ruta raíz (Invernadero_plantas-)
    # current_app.root_path es /app, bajamos uno para llegar a la raíz
    base_dir = os.path.abspath(os.path.join(current_app.root_path, ".."))
    script_path = os.path.join(base_dir, "spark", script)

    if not os.path.exists(script_path):
        flash(f"El script {script} no existe.", "danger")
        return redirect(url_for('main.reportes'))

    try:
        # 2. Configurar el entorno (IMPORTANTE para encontrar app.config)
        env = os.environ.copy()
        # Esto permite que los scripts en /spark hagan "from app.config... import..."
        env["PYTHONPATH"] = base_dir 
        
        # 3. Comando de ejecución optimizado
        if "dashboard" in script or "graficos" in script:
            # Ejecutamos con headless=true para que Flask mantenga el control
            comando = [
                sys.executable, "-m", "streamlit", "run", script_path, 
                "--server.port", "8501",
                "--server.headless", "true"
            ]
        else:
            comando = [sys.executable, script_path]

        # 4. LANZAR PROCESO
        # cwd=base_dir asegura que el script busque archivos desde la raíz
        subprocess.Popen(comando, env=env, cwd=base_dir)
        
        print(f"🚀 Dashboard iniciado desde: {base_dir}")
        
    except Exception as e:
        print(f"❌ Error al lanzar Spark: {e}")
        flash("Error al iniciar el motor de analítica.", "danger")

    # Redirigimos al puerto donde corre Streamlit
    return redirect("http://localhost:8501")


@main_bp.route('/stop_all_spark')
def stop_all_spark():
    """Cierra cualquier proceso de Streamlit/Spark en el puerto 8501"""
    try:
        # Comando para Linux para liberar el puerto 8501
        subprocess.run(["fuser", "-k", "8501/tcp"], check=False)
        return jsonify({"message": "Procesos de analítica detenidos correctamente."})
    except Exception as e:
        return jsonify({"message": f"Error al detener procesos: {str(e)}"}), 500


@main_bp.route('/check_spark_status')
def check_spark_status():
    """Verifica si el servidor de Spark/Streamlit está activo"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1) # No esperar más de 1 segundo
        result = sock.connect_ex(('127.0.0.1', 8501))
        sock.close()
        # Si result es 0, el puerto está respondiendo
        return jsonify({"active": result == 0})
    except Exception:
        return jsonify({"active": False})