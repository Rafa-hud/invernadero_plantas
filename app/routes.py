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

def detectar_usb_json():
    """Detección USB mantenida exactamente igual para conservar su robustez"""
    sistema = platform.system()
    resultado = {
        'conectado': False, 'ruta': None, 'espacio_libre': 0,
        'espacio_total': 0, 'sistema': sistema, 'dispositivos': []
    }
    
    try:
        if sistema == 'Windows':
            for particion in psutil.disk_partitions():
                if particion.mountpoint.lower() == 'c:\\':
                    continue
                if 'removable' in particion.opts.lower():
                    try:
                        uso = psutil.disk_usage(particion.mountpoint)
                        if uso.total > 0:
                            resultado.update({
                                'conectado': True, 'ruta': particion.mountpoint,
                                'espacio_libre': round(uso.free / (1024**3), 2),
                                'espacio_total': round(uso.total / (1024**3), 2)
                            })
                            break
                    except: continue
            
            if not resultado['conectado']:
                for letra in string.ascii_uppercase:
                    drive = f"{letra}:\\"
                    try:
                        if os.path.exists(drive) and windll.kernel32.GetDriveTypeW(drive) == 2:
                            uso = psutil.disk_usage(drive)
                            if uso.total > 0:
                                resultado.update({
                                    'conectado': True, 'ruta': drive,
                                    'espacio_libre': round(uso.free / (1024**3), 2),
                                    'espacio_total': round(uso.total / (1024**3), 2)
                                })
                                break
                    except: continue
                        
        elif sistema == 'Linux':
            posibles_rutas = ['/media', '/mnt', '/run/media', '/media/$USER', '/mnt/usb']
            for ruta_base in posibles_rutas:
                ruta_expandida = os.path.expanduser(ruta_base.replace('$USER', os.getenv('USER', '')))
                if os.path.exists(ruta_expandida):
                    try:
                        for item in os.listdir(ruta_expandida):
                            path_completo = os.path.join(ruta_expandida, item)
                            if os.path.ismount(path_completo):
                                uso = psutil.disk_usage(path_completo)
                                if uso.total > 0:
                                    resultado.update({
                                        'conectado': True, 'ruta': path_completo,
                                        'espacio_libre': round(uso.free / (1024**3), 2),
                                        'espacio_total': round(uso.total / (1024**3), 2)
                                    })
                                    break
                    except: continue
                if resultado['conectado']: break
                    
        elif sistema == 'Darwin':
            posibles_rutas = ['/Volumes']
            for ruta_base in posibles_rutas:
                if os.path.exists(ruta_base):
                    try:
                        for item in os.listdir(ruta_base):
                            path_completo = os.path.join(ruta_base, item)
                            if not item.startswith('.') and os.path.ismount(path_completo):
                                uso = psutil.disk_usage(path_completo)
                                if uso.total > 0:
                                    resultado.update({
                                        'conectado': True, 'ruta': path_completo,
                                        'espacio_libre': round(uso.free / (1024**3), 2),
                                        'espacio_total': round(uso.total / (1024**3), 2)
                                    })
                                    break
                    except: continue
                if resultado['conectado']: break
        
        # Fallback universal
        if not resultado['conectado']:
            for particion in psutil.disk_partitions():
                mountpoint = particion.mountpoint
                system_paths = ['/', '/boot', '/home', '/var', '/usr', '/etc', 'C:\\', '/System', '/Library']
                if not any(mountpoint.startswith(sys_path) for sys_path in system_paths):
                    try:
                        uso = psutil.disk_usage(mountpoint)
                        if uso.total > 0 and uso.total < 2 * 1024**4:
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
@plants_bp.route('/')
@login_required
def listar_plantas():
    if current_user.rol == 'cliente':
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('tienda.tienda_index'))
    
    if current_user.rol == 'admin':
        plantas = PlantaModel.get_all()
    else:
        plantas = PlantaModel.get_by_usuario(current_user.id)
    
    return render_template('plants/lista.html', plantas=plantas)

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
    if current_user.rol != 'cliente': return redirect(url_for('main.dashboard'))
    
    # MONGODB: Creamos un método para traer las disponibles (stock > 0, disponible_venta = True)
    plantas_disponibles = PlantaModel.get_disponibles()
    categorias = PlantaModel.get_categorias_disponibles()
    
    return render_template('tienda/index.html', plantas=plantas_disponibles, categorias=categorias)

@tienda_bp.route('/planta/<id>')
@login_required
def ver_planta_tienda(id):
    planta = PlantaModel.get_by_id(id)
    plantas_relacionadas = PlantaModel.get_by_categoria(planta.get('categoria'), exclude_id=id, limit=4)
    return render_template('tienda/detalle_planta.html', planta=planta, plantas_relacionadas=plantas_relacionadas)

@tienda_bp.route('/buscar')
@login_required
def buscar_plantas():
    query = request.args.get('q', '')
    precio_min = request.args.get('precio_min', type=float)
    precio_max = request.args.get('precio_max', type=float)
    categoria = request.args.get('categoria', '')
    
    # MONGODB: Idealmente usarías un método de búsqueda avanzado en PlantaModel
    # que utilice expresiones regulares ($regex) para buscar en texto.
    plantas = PlantaModel.buscar_avanzada(query, precio_min, precio_max, categoria)
    categorias = PlantaModel.get_categorias_disponibles()
    
    return render_template('tienda/buscar.html', plantas=plantas, query=query, 
                         categorias=categorias, categoria_seleccionada=categoria)


@tienda_bp.route('/mi-perfil')
@login_required
def mi_perfil():
    # Asegúrate de tener el archivo templates/tienda/perfil.html creado
    return render_template('tienda/perfil.html', usuario=current_user)


# ========== CARRITO DE COMPRAS ==========
@tienda_bp.route('/carrito')
@login_required
def ver_carrito():
    carrito = obtener_carrito()
    plantas_carrito = []
    subtotal = 0.0
    
    for planta_id_str, item in carrito.items():
        planta = PlantaModel.get_by_id(planta_id_str)
        if planta and planta.get('disponible_venta') and planta.get('stock', 0) > 0:
            precio_unitario = float(planta.get('precio', 0))
            cantidad = item['cantidad']
            total_item = cantidad * precio_unitario
            
            planta_dict = dict(planta) # Copia superficial
            planta_dict['id'] = str(planta['_id']) # Para el template
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

@tienda_bp.route('/carrito/agregar/<id>', methods=['POST'])
@login_required
def agregar_al_carrito(id):
    planta = PlantaModel.get_by_id(id)
    if not planta or not planta.get('disponible_venta'): return jsonify({'success': False}), 404
    
    cantidad = request.json.get('cantidad', 1)
    carrito = obtener_carrito()
    
    if id in carrito:
        carrito[id]['cantidad'] += cantidad
    else:
        carrito[id] = {'cantidad': cantidad, 'precio': str(planta['precio'])}
        
    guardar_carrito(carrito)
    return jsonify({'success': True, 'carrito_count': sum(i['cantidad'] for i in carrito.values())})

# (Omito por brevedad las rutas de /vaciar, /actualizar y /eliminar del carrito, 
# la lógica es idéntica a tu código pero usando el `id` como string del diccionario).

# ========== CHECKOUT (EL GRAN CAMBIO) ==========
@tienda_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    carrito = obtener_carrito()
    if not carrito: return redirect(url_for('tienda.ver_carrito'))
    
    subtotal = 0.0
    detalles_pedido = []
    
    # Pre-calculamos y validamos stock
    for planta_id_str, item in carrito.items():
        planta = PlantaModel.get_by_id(planta_id_str)
        if planta:
            if planta['stock'] < item['cantidad']:
                flash(f'Stock insuficiente para {planta["nombre"]}', 'danger')
                return redirect(url_for('tienda.ver_carrito'))
            
            subtotal += float(planta['precio']) * item['cantidad']
            # Construimos el array embebido para MongoDB
            detalles_pedido.append({
                'id_planta': ObjectId(planta_id_str),
                'nombre_planta': planta['nombre'], # Desnormalizamos el nombre por practicidad
                'cantidad': item['cantidad'],
                'precio_en_compra': float(planta['precio'])
            })
            
    envio = 5.99 if subtotal < 50 else 0
    total = subtotal + envio + (subtotal * 0.12)
    
    if request.method == 'POST':
        try:
            # 1. Crear el documento completo del pedido con sus detalles embebidos
            nuevo_pedido = {
                'id_cliente': ObjectId(current_user.id),
                'costo_total': total,
                'estado_pedido': 'pendiente',
                'fecha_orden': datetime.utcnow(),
                'direccion_envio': request.form.get('direccion_envio'),
                'telefono_contacto': request.form.get('telefono_contacto'),
                'metodo_pago': request.form.get('metodo_pago'),
                'detalles': detalles_pedido # ¡Aquí incrustamos la tabla "pedido_detalle" directamente!
            }
            
            pedido_id = PedidoModel.create(nuevo_pedido)
            
            # 2. Actualizar stock de las plantas
            for detalle in detalles_pedido:
                planta_bd = PlantaModel.get_by_id(str(detalle['id_planta']))
                nuevo_stock = planta_bd['stock'] - detalle['cantidad']
                disponible = nuevo_stock > 0
                PlantaModel.update(str(detalle['id_planta']), {'stock': nuevo_stock, 'disponible_venta': disponible})
            
            guardar_carrito({}) # Vaciar carrito
            flash(f'¡Pedido realizado exitosamente!', 'success')
            return redirect(url_for('tienda.mis_pedidos'))
            
        except Exception as e:
            flash(f'Error al procesar el pedido: {str(e)}', 'danger')
            
    return render_template('tienda/checkout.html', subtotal=subtotal, total=total)

@tienda_bp.route('/mis-pedidos')
@login_required
def mis_pedidos():
    pedidos = PedidoModel.get_by_usuario(current_user.id)
    return render_template('tienda/mis_pedidos.html', pedidos=pedidos)

# routes.py (PARTE 3: Pedidos, Dashboard y Estadísticas Analíticas)

# ========== MAIN ROUTES (DASHBOARD) ==========
@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.rol == 'cliente':
        return redirect(url_for('tienda.tienda_index'))
    
    db = get_db()
    
    # Conteos rápidos usando PyMongo
    total_plantas = db.plants.count_documents({})
    plantas_activas = db.plants.count_documents({'estado': 'activa'})
    
    # Obtener últimos riegos (usando aggregate con $lookup es posible, 
    # pero para simplicidad traemos los logs y buscamos los nombres)
    ultimos_riegos = list(db.watering_logs.find().sort('fecha_riego', -1).limit(10))
    for riego in ultimos_riegos:
        planta = db.plants.find_one({'_id': riego['id_planta']})
        riego['nombre_planta'] = planta['nombre'] if planta else 'Desconocida'
    
    ultimo_backup = db.backups.find_one(sort=[('fecha_respaldo', -1)])
    ultimo_backup_fecha = ultimo_backup['fecha_respaldo'] if ultimo_backup else None
    
    return render_template('dashboard.html',
                         total_plantas=total_plantas,
                         plantas_riego_hoy=plantas_activas,
                         ultimos_riegos=ultimos_riegos,
                         ultimo_backup=ultimo_backup_fecha)



#
#
#-----------------------------------------------------------------------------------
# ========== ADMIN - GESTIÓN DE PEDIDOS ==========
from bson import ObjectId
from flask import request, jsonify, render_template, redirect, url_for, flash
from datetime import datetime

@main_bp.route('/admin/pedidos')
@login_required
def admin_pedidos():
    if current_user.rol != 'admin': 
        return redirect(url_for('main.dashboard'))
    
    db = get_db()
    estado = request.args.get('estado', 'todos')
    query = {} if estado == 'todos' else {'estado_pedido': estado}
    
    pedidos = list(db.orders.find(query).sort('fecha_orden', -1))
    
    for pedido in pedidos:
        # --- Lógica de Cliente (para evitar el error anterior) ---
        u = db.users.find_one({'_id': pedido.get('id_cliente')})
        pedido['cliente'] = u if u else {'nombre': 'Usuario Eliminado', 'correo': 'N/A'}
        
        # --- Lógica de Detalles/Plantas (para evitar el error ACTUAL) ---
        # Recorremos los detalles para asegurar que exista el objeto 'planta'
        detalles_procesados = []
        for det in pedido.get('detalles', []):
            # Si el HTML busca 'detalle.planta.nombre', creamos esa estructura
            if 'planta' not in det:
                det['planta'] = {'nombre': det.get('nombre', 'Planta desconocida')}
            detalles_procesados.append(det)
        
        pedido['detalles'] = detalles_procesados
            
    return render_template('admin/pedidos.html', pedidos=pedidos, estado=estado)

@main_bp.route('/admin/pedido/<id>')
@login_required
def admin_ver_pedido(id):
    if current_user.rol != 'admin': 
        return redirect(url_for('main.dashboard'))
    
    db = get_db()
    try:
        # Buscamos el pedido específico convirtiendo el ID de texto a ObjectId
        pedido = db.orders.find_one({'_id': ObjectId(id)})
        if not pedido:
            flash('Pedido no encontrado', 'danger')
            return redirect(url_for('main.admin_pedidos'))
        
        # Buscamos los datos del cliente para mostrar en el detalle
        cliente = db.users.find_one({'_id': pedido.get('id_cliente')})
        pedido['cliente'] = cliente
        
        # Los detalles (plantas compradas) ya están en pedido['detalles'] gracias a MongoDB
        return render_template('admin/detalle_pedido.html', 
                               pedido=pedido, 
                               detalles=pedido.get('detalles', []))
    except Exception as e:
        flash(f'Error al cargar el pedido: {str(e)}', 'danger')
        return redirect(url_for('main.admin_pedidos'))

@main_bp.route('/admin/pedido/<id>/actualizar-estado', methods=['POST'])
@login_required
def actualizar_estado_pedido(id):
    if current_user.rol != 'admin': 
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    db = get_db()
    data = request.get_json()
    nuevo_estado = data.get('estado', '')
    
    estados_validos = ['pendiente', 'procesando', 'enviado', 'completado', 'cancelado']
    if nuevo_estado not in estados_validos:
        return jsonify({'success': False, 'message': 'Estado inválido'}), 400
    
    try:
        # 1. Obtener el estado anterior para saber si debemos ajustar stock
        pedido_actual = db.orders.find_one({'_id': ObjectId(id)})
        if not pedido_actual:
            return jsonify({'success': False, 'message': 'Pedido no encontrado'}), 404

        # 2. Lógica especial para CANCELACIÓN (Devolver stock)
        # Si el pedido no estaba cancelado y ahora se cancela, devolvemos las plantas al stock
        if nuevo_estado == 'cancelado' and pedido_actual.get('estado_pedido') != 'cancelado':
            for item in pedido_actual.get('detalles', []):
                db.plants.update_one(
                    {'_id': item['planta_id']}, 
                    {'$inc': {'stock': item['cantidad']}} # Incrementa el stock
                )

        # 3. Preparar los campos de actualización
        update_fields = {'estado_pedido': nuevo_estado}
        if nuevo_estado == 'enviado':
            update_fields['fecha_envio'] = datetime.utcnow()
        elif nuevo_estado == 'completado':
            update_fields['fecha_completado'] = datetime.utcnow()
        
        # 4. Guardar cambios en la base de datos
        db.orders.update_one({'_id': ObjectId(id)}, {'$set': update_fields})
        
        return jsonify({
            'success': True,
            'message': f'Pedido actualizado a {nuevo_estado}',
            'estado': nuevo_estado
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    
    
    
    
#
#-----------------------------------------------------------------------------
# ========== ADMIN - ESTADÍSTICAS TIENDA (AGGREGATION PIPELINES) ==========
@main_bp.route('/admin/estadisticas-tienda')
@login_required
def estadisticas_tienda():
    if current_user.rol != 'admin': return redirect(url_for('main.dashboard'))
    
    db = get_db()
    
    # 1. Ventas totales y ticket promedio (Pipeline)
    ventas_pipeline = [
        {'$match': {'estado_pedido': {'$ne': 'cancelado'}}},
        {'$group': {
            '_id': None, 
            'ventas_totales': {'$sum': '$costo_total'},
            'total_pedidos': {'$sum': 1}
        }}
    ]
    ventas_result = list(db.orders.aggregate(ventas_pipeline))
    stats_generales = ventas_result[0] if ventas_result else {'ventas_totales': 0, 'total_pedidos': 0}
    
    # 2. Pedidos por estado
    pedidos_pendientes = db.orders.count_documents({'estado_pedido': 'pendiente'})
    pedidos_procesando = db.orders.count_documents({'estado_pedido': 'procesando'})
    pedidos_completados = db.orders.count_documents({'estado_pedido': 'completado'})
    pedidos_cancelados = db.orders.count_documents({'estado_pedido': 'cancelado'})
    
    # 3. Productos más vendidos (El poder de $unwind)
    # $unwind "desempaqueta" el array de detalles para poder sumarlos
    productos_pipeline = [
        {'$match': {'estado_pedido': {'$ne': 'cancelado'}}},
        {'$unwind': '$detalles'},
        {'$group': {
            '_id': '$detalles.id_planta',
            'nombre': {'$first': '$detalles.nombre_planta'},
            'total_vendido': {'$sum': '$detalles.cantidad'},
            'ingresos': {'$sum': {'$multiply': ['$detalles.cantidad', '$detalles.precio_en_compra']}}
        }},
        {'$sort': {'total_vendido': -1}},
        {'$limit': 10}
    ]
    productos_vendidos_list = list(db.orders.aggregate(productos_pipeline))
    
    # 4. Ventas mensuales (últimos 6 meses)
    seis_meses_atras = datetime.utcnow() - timedelta(days=180)
    mensuales_pipeline = [
        {'$match': {
            'fecha_orden': {'$gte': seis_meses_atras},
            'estado_pedido': {'$ne': 'cancelado'}
        }},
        {'$group': {
            # Extraemos el Año-Mes de la fecha ISO
            '_id': {'$dateToString': {'format': '%Y-%m', 'date': '$fecha_orden'}},
            'total_pedidos': {'$sum': 1},
            'ventas_totales': {'$sum': '$costo_total'}
        }},
        {'$sort': {'_id': 1}}
    ]
    ventas_mensuales_raw = list(db.orders.aggregate(mensuales_pipeline))
    
    # Formatear meses a español
    meses_espanol = {'01':'Enero', '02':'Febrero', '03':'Marzo', '04':'Abril', '05':'Mayo', '06':'Junio', 
                     '07':'Julio', '08':'Agosto', '09':'Septiembre', '10':'Octubre', '11':'Noviembre', '12':'Diciembre'}
    ventas_mensuales = []
    for v in ventas_mensuales_raw:
        anio, mes_num = v['_id'].split('-')
        ventas_mensuales.append({
            'mes': f"{meses_espanol.get(mes_num, mes_num)} {anio}",
            'total_pedidos': v['total_pedidos'],
            'ventas_totales': v['ventas_totales']
        })
    
    # 5. Estadísticas de clientes
    total_clientes = db.users.count_documents({'rol': 'cliente'})
    clientes_activos = len(db.orders.distinct('id_cliente'))
    ticket_promedio = stats_generales['ventas_totales'] / stats_generales['total_pedidos'] if stats_generales['total_pedidos'] > 0 else 0
    tasa_conversion = (clientes_activos / total_clientes * 100) if total_clientes > 0 else 0
    total_historico = stats_generales['total_pedidos'] + pedidos_cancelados
    tasa_cancelacion = (pedidos_cancelados / total_historico * 100) if total_historico > 0 else 0
    
    return render_template('admin/estadisticas_tienda.html',
                         ventas_totales=stats_generales['ventas_totales'],
                         total_pedidos=stats_generales['total_pedidos'],
                         pedidos_pendientes=pedidos_pendientes,
                         pedidos_procesando=pedidos_procesando,
                         pedidos_completados=pedidos_completados,
                         pedidos_cancelados=pedidos_cancelados,
                         productos_vendidos=productos_vendidos_list,
                         ventas_mensuales=ventas_mensuales,
                         total_clientes=total_clientes,
                         clientes_activos=clientes_activos,
                         ticket_promedio=ticket_promedio,
                         tasa_conversion=tasa_conversion,
                         tasa_cancelacion=tasa_cancelacion)

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
        flash('Solo administradores pueden restaurar', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    db = get_db()
    respaldo = db.backups.find_one({'_id': ObjectId(id)})
    
    if not respaldo or not os.path.exists(respaldo['ruta_archivo']):
        flash('❌ El archivo no existe', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    try:
        # 1. DESCOMPRESIÓN Y LECTURA
        with gzip.open(respaldo['ruta_archivo'], 'rt', encoding='utf-8') as f_in:
            backup_data = json_util.loads(f_in.read())
        
        # 2. RESTAURACIÓN EN MONGODB (Reemplaza a mysql import)
        for coll_name, documentos in backup_data.items():
            if documentos:
                # Opcional: Limpiar la colección actual antes de restaurar
                db[coll_name].delete_many({}) 
                # Insertar los documentos respaldados
                db[coll_name].insert_many(documentos)
        
        # Registrar en el historial
        db.access_logs.insert_one({
            'usuario_id': ObjectId(current_user.id),
            'accion': f'restaurar_respaldo_{id}',
            'fecha_acceso': datetime.utcnow()
        })
        
        flash('✅ Base de datos restaurada exitosamente', 'success')
    except Exception as e:
        flash(f'❌ Error al restaurar: {str(e)}', 'danger')
        
    return redirect(url_for('backup.listar_respaldos'))

@backup_bp.route('/eliminar/<id>', methods=['POST'])
@login_required
def eliminar_respaldo(id):
    if current_user.rol != 'admin': return redirect(url_for('backup.listar_respaldos'))
    
    db = get_db()
    respaldo = db.backups.find_one({'_id': ObjectId(id)})
    
    try:
        if respaldo and os.path.exists(respaldo['ruta_archivo']):
            os.remove(respaldo['ruta_archivo'])
        
        db.backups.delete_one({'_id': ObjectId(id)})
        flash('✅ Respaldo eliminado exitosamente', 'success')
    except Exception as e:
        flash(f'❌ Error al eliminar: {str(e)}', 'danger')
        
    return redirect(url_for('backup.listar_respaldos'))


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