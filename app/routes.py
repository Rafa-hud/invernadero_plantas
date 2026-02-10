# routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import Usuario, Planta, RegistroRiego, Respaldo, HistorialAcceso, Pedido, PedidoDetalle, ProgramacionRespaldo
from datetime import datetime, timedelta, date
import os
import traceback
import gzip
import shutil
import hashlib
from werkzeug.utils import secure_filename
import json
import platform
import psutil
import subprocess
import tempfile
from ctypes import windll
import string
import sys

# Blueprints
auth_bp = Blueprint('auth', __name__)
main_bp = Blueprint('main', __name__)
plants_bp = Blueprint('plants', __name__)
backup_bp = Blueprint('backup', __name__)
reports_bp = Blueprint('reports', __name__)
tienda_bp = Blueprint('tienda', __name__)  # Blueprint para tienda

# ========== CONFIGURACIÓN DE RESPALDOS ==========
BACKUP_FOLDER = 'backups'
ALLOWED_EXTENSIONS = {'sql', 'gz'}

# Asegurar que la carpeta de respaldos existe
if not os.path.exists(BACKUP_FOLDER):
    os.makedirs(BACKUP_FOLDER, exist_ok=True)

# ========== FUNCIONES AUXILIARES MEJORADAS ==========
def obtener_carrito():
    """Obtener el carrito de la sesión"""
    if 'carrito' not in session:
        session['carrito'] = {}
    return session['carrito']

def guardar_carrito(carrito):
    """Guardar el carrito en la sesión"""
    session['carrito'] = carrito
    session.modified = True

def calcular_checksum(filepath):
    """Calcular checksum SHA-256 de un archivo - VERSIÓN ROBUSTA"""
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
    """Verificar si el archivo tiene extensión permitida"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validar_ruta_segura(ruta):
    """Validar que una ruta sea segura para operaciones USB"""
    if not ruta:
        return False
    
    # Normalizar ruta
    ruta = os.path.abspath(ruta)
    
    # Lista de rutas prohibidas del sistema
    rutas_prohibidas = [
        '/', '/etc', '/bin', '/usr', '/var', '/root', '/home',
        '/lib', '/opt', '/sbin', '/sys', '/proc', '/dev',
        'C:\\', 'C:\\Windows', 'C:\\Program Files', 'C:\\Program Files (x86)',
        'C:\\Users', 'C:\\System32', 'C:\\Windows\\System32'
    ]
    
    # Verificar que no sea una ruta del sistema
    for prohibida in rutas_prohibidas:
        if ruta.startswith(prohibida):
            return False
    
    # Verificar que exista
    return os.path.exists(ruta)

def detectar_usb_json():
    """Detectar USB - VERSIÓN MEJORADA Y FUNCIONAL"""
    sistema = platform.system()
    resultado = {
        'conectado': False,
        'ruta': None,
        'espacio_libre': 0,
        'espacio_total': 0,
        'sistema': sistema,
        'dispositivos': []
    }
    
    try:
        current_app.logger.info(f"🔍 Detectando USB en sistema: {sistema}")
        
        if sistema == 'Windows':
            current_app.logger.info("🪟 Sistema Windows detectado")
            
            # Método 1: Usar psutil para detectar particiones removibles
            for particion in psutil.disk_partitions():
                current_app.logger.info(f"  Partición: {particion.device} -> {particion.mountpoint} (Tipo: {particion.fstype}, Opciones: {particion.opts})")
                
                # Filtrar particiones del sistema (C:, D: de CD-ROM, etc.)
                if particion.mountpoint.lower() == 'c:\\':
                    continue
                    
                # Verificar si es removible (opción más confiable en Windows)
                if 'removable' in particion.opts.lower():
                    try:
                        uso = psutil.disk_usage(particion.mountpoint)
                        if uso.total > 0:
                            resultado['conectado'] = True
                            resultado['ruta'] = particion.mountpoint
                            resultado['espacio_libre'] = round(uso.free / (1024**3), 2)
                            resultado['espacio_total'] = round(uso.total / (1024**3), 2)
                            
                            resultado['dispositivos'].append({
                                'ruta': particion.mountpoint,
                                'tipo': particion.fstype or 'desconocido',
                                'opts': particion.opts,
                                'espacio_libre_gb': round(uso.free / (1024**3), 2),
                                'espacio_total_gb': round(uso.total / (1024**3), 2)
                            })
                            current_app.logger.info(f"  ✅ USB detectado: {particion.mountpoint}")
                            break
                    except Exception as e:
                        current_app.logger.error(f"  ❌ Error accediendo a {particion.mountpoint}: {e}")
                        continue
            
            # Método 2: Verificar letras de unidad manualmente (fallback)
            if not resultado['conectado']:
                current_app.logger.info("  Método 2: Verificando letras de unidad...")
                for letra in string.ascii_uppercase:
                    drive = f"{letra}:\\"
                    try:
                        if os.path.exists(drive):
                            # Obtener tipo de unidad usando windll (Windows API)
                            drive_type = windll.kernel32.GetDriveTypeW(drive)
                            # DRIVE_REMOVABLE = 2
                            if drive_type == 2:
                                uso = psutil.disk_usage(drive)
                                if uso.total > 0:
                                    resultado['conectado'] = True
                                    resultado['ruta'] = drive
                                    resultado['espacio_libre'] = round(uso.free / (1024**3), 2)
                                    resultado['espacio_total'] = round(uso.total / (1024**3), 2)
                                    current_app.logger.info(f"  ✅ USB detectado (API Windows): {drive}")
                                    break
                    except Exception as e:
                        current_app.logger.debug(f"  Disco {drive} no accesible: {e}")
                        continue
                        
        elif sistema == 'Linux':
            current_app.logger.info("🐧 Sistema Linux detectado")
            
            # Método para Linux
            posibles_rutas = ['/media', '/mnt', '/run/media', '/media/$USER', '/mnt/usb']
            
            for ruta_base in posibles_rutas:
                ruta_expandida = os.path.expanduser(ruta_base.replace('$USER', os.getenv('USER', '')))
                if os.path.exists(ruta_expandida):
                    current_app.logger.info(f"  Buscando en: {ruta_expandida}")
                    try:
                        items = os.listdir(ruta_expandida)
                        for item in items:
                            path_completo = os.path.join(ruta_expandida, item)
                            if os.path.ismount(path_completo):
                                try:
                                    uso = psutil.disk_usage(path_completo)
                                    if uso.total > 0:
                                        resultado['conectado'] = True
                                        resultado['ruta'] = path_completo
                                        resultado['espacio_libre'] = round(uso.free / (1024**3), 2)
                                        resultado['espacio_total'] = round(uso.total / (1024**3), 2)
                                        
                                        resultado['dispositivos'].append({
                                            'ruta': path_completo,
                                            'nombre': item,
                                            'espacio_libre_gb': round(uso.free / (1024**3), 2),
                                            'espacio_total_gb': round(uso.total / (1024**3), 2)
                                        })
                                        current_app.logger.info(f"  ✅ USB detectado: {path_completo}")
                                        break
                                except Exception as e:
                                    current_app.logger.error(f"  ❌ Error en {path_completo}: {e}")
                                    continue
                    except Exception as e:
                        current_app.logger.error(f"  ❌ Error listando {ruta_expandida}: {e}")
                        continue
                
                if resultado['conectado']:
                    break
                    
        elif sistema == 'Darwin':  # macOS
            current_app.logger.info("🍎 Sistema macOS detectado")
            posibles_rutas = ['/Volumes']
            
            for ruta_base in posibles_rutas:
                if os.path.exists(ruta_base):
                    current_app.logger.info(f"  Buscando en: {ruta_base}")
                    try:
                        for item in os.listdir(ruta_base):
                            path_completo = os.path.join(ruta_base, item)
                            # En macOS, evitar directorios del sistema
                            if not item.startswith('.') and os.path.ismount(path_completo):
                                try:
                                    uso = psutil.disk_usage(path_completo)
                                    if uso.total > 0:
                                        resultado['conectado'] = True
                                        resultado['ruta'] = path_completo
                                        resultado['espacio_libre'] = round(uso.free / (1024**3), 2)
                                        resultado['espacio_total'] = round(uso.total / (1024**3), 2)
                                        current_app.logger.info(f"  ✅ USB detectado: {path_completo}")
                                        break
                                except Exception as e:
                                    current_app.logger.error(f"  ❌ Error en {path_completo}: {e}")
                                    continue
                    except Exception as e:
                        current_app.logger.error(f"  ❌ Error listando {ruta_base}: {e}")
                        continue
                
                if resultado['conectado']:
                    break
        
        # Método de respaldo universal: buscar cualquier punto de montaje que no sea del sistema
        if not resultado['conectado']:
            current_app.logger.info("  Método de respaldo: Buscando cualquier punto de montaje...")
            for particion in psutil.disk_partitions():
                mountpoint = particion.mountpoint
                # Excluir rutas del sistema
                system_paths = ['/', '/boot', '/home', '/var', '/usr', '/etc', 'C:\\', '/System', '/Library']
                if not any(mountpoint.startswith(sys_path) for sys_path in system_paths):
                    try:
                        uso = psutil.disk_usage(mountpoint)
                        # Heurística: menos de 2TB (tamaño típico de USB)
                        if uso.total > 0 and uso.total < 2 * 1024**4:
                            resultado['conectado'] = True
                            resultado['ruta'] = mountpoint
                            resultado['espacio_libre'] = round(uso.free / (1024**3), 2)
                            resultado['espacio_total'] = round(uso.total / (1024**3), 2)
                            current_app.logger.info(f"  ✅ Dispositivo encontrado (respaldo): {mountpoint}")
                            break
                    except Exception as e:
                        current_app.logger.debug(f"  Error en {mountpoint}: {e}")
        
    except Exception as e:
        current_app.logger.error(f"❌ Error crítico detectando USB: {e}")
        resultado['error'] = str(e)
    
    current_app.logger.info(f"📊 Resultado USB: conectado={resultado['conectado']}, ruta={resultado['ruta']}")
    return resultado

def crear_backup_folder_usb(usb_path):
    """Crear carpeta de respaldos en USB si no existe"""
    try:
        usb_backup_folder = os.path.join(usb_path, 'respaldos_gestion_plantas')
        os.makedirs(usb_backup_folder, exist_ok=True)
        current_app.logger.info(f"📁 Carpeta creada: {usb_backup_folder}")
        return usb_backup_folder
    except Exception as e:
        current_app.logger.error(f"Error creando carpeta USB: {e}")
        raise

# ========== RUTAS USB MEJORADAS ==========

@backup_bp.route('/detectar-usb')
@login_required
def detectar_usb():
    """Endpoint para detectar USB - VERSIÓN FUNCIONAL"""
    try:
        if current_user.rol != 'admin':
            return jsonify({
                'success': False,
                'message': 'Solo administradores pueden acceder a esta función',
                'conectado': False
            }), 403
        
        usb_info = detectar_usb_json()
        
        return jsonify({
            'success': True,
            **usb_info
        })
        
    except Exception as e:
        current_app.logger.error(f"Error en detectar_usb: {e}")
        return jsonify({
            'success': False,
            'conectado': False,
            'error': str(e),
            'message': 'Error detectando dispositivo USB'
        }), 500

@backup_bp.route('/forzar-detectar-usb')
@login_required
def forzar_detectar_usb():
    """Forzar detección de USB y recargar página"""
    if current_user.rol != 'admin':
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    # Forzar detección
    usb_info = detectar_usb_json()
    
    if usb_info['conectado']:
        flash(f'USB detectado: {usb_info["ruta"]} ({usb_info["espacio_libre"]} GB libres)', 'success')
    else:
        flash('No se detectó ninguna unidad USB. Conecta una unidad e intenta nuevamente.', 'warning')
    
    return redirect(url_for('backup.listar_respaldos'))

@backup_bp.route('/estado-usb-detallado')
@login_required
def estado_usb_detallado():
    """Obtener estado detallado del USB"""
    try:
        if current_user.rol != 'admin':
            return jsonify({'success': False, 'message': 'No autorizado'}), 403
        
        usb_info = detectar_usb_json()
        
        if not usb_info.get('conectado'):
            return jsonify({
                'success': True,
                'conectado': False,
                'message': 'No hay dispositivos USB conectados',
                'timestamp': datetime.utcnow().isoformat()
            })
        
        usb_path = usb_info['ruta']
        
        # Información detallada del sistema de archivos
        espacio = psutil.disk_usage(usb_path)
        
        # Información de respaldos en USB
        respaldos_usb = Respaldo.query.filter_by(almacenamiento='usb').all()
        
        # Calcular espacio utilizado por respaldos
        espacio_respaldos_mb = sum(r.tamaño_mb or 0 for r in respaldos_usb)
        
        respuesta = {
            'success': True,
            'conectado': True,
            'dispositivo': {
                'ruta': usb_path,
                'sistema': usb_info.get('sistema', 'desconocido'),
                'espacio_total_gb': round(espacio.total / (1024**3), 2),
                'espacio_usado_gb': round(espacio.used / (1024**3), 2),
                'espacio_libre_gb': round(espacio.free / (1024**3), 2),
                'porcentaje_usado': round((espacio.used / espacio.total) * 100, 2),
                'porcentaje_libre': round((espacio.free / espacio.total) * 100, 2)
            },
            'respaldos': {
                'total_en_usb': len(respaldos_usb),
                'espacio_utilizado_mb': round(espacio_respaldos_mb, 2),
                'espacio_utilizado_gb': round(espacio_respaldos_mb / 1024, 2),
                'porcentaje_espacio_usb': round((espacio_respaldos_mb * 1024 * 1024 / espacio.total) * 100, 2) if espacio.total > 0 else 0
            },
            'recomendaciones': [],
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Agregar recomendaciones basadas en el estado
        if espacio.free < 500 * 1024 * 1024:  # Menos de 500MB libres
            respuesta['recomendaciones'].append('⚠️ El USB tiene poco espacio libre. Considera liberar espacio.')
        
        if len(respaldos_usb) == 0:
            respuesta['recomendaciones'].append('💡 No hay respaldos en el USB. Considera copiar algunos respaldos locales.')
        
        return jsonify(respuesta)
        
    except Exception as e:
        current_app.logger.error(f"Error en estado_usb_detallado: {e}")
        return jsonify({
            'success': False,
            'message': f'Error obteniendo estado USB: {str(e)}'
        }), 500

@backup_bp.route('/test-usb-permisos')
@login_required
def test_usb_permisos():
    """Testear permisos de USB"""
    try:
        if current_user.rol != 'admin':
            return jsonify({'success': False, 'message': 'No autorizado'}), 403
        
        usb_info = detectar_usb_json()
        if not usb_info.get('conectado'):
            return jsonify({
                'success': False,
                'message': 'No hay dispositivo USB conectado',
                'conectado': False
            })
        
        usb_path = usb_info['ruta']
        
        # Validar ruta segura
        if not validar_ruta_segura(usb_path):
            return jsonify({
                'success': False,
                'message': 'Ruta de USB no segura',
                'usb_path': usb_path
            }), 400
        
        resultados = {
            'success': True,
            'usb_path': usb_path,
            'escritura_ok': False,
            'carpeta_ok': False,
            'permisos': {}
        }
        
        # Probar escritura en archivo temporal
        test_filename = None
        try:
            test_filename = os.path.join(usb_path, f'test_usb_{datetime.now().strftime("%Y%m%d_%H%M%S")}.tmp')
            with open(test_filename, 'w') as f:
                f.write('test_usb_permissions')
            
            # Verificar que el archivo se escribió
            if os.path.exists(test_filename) and os.path.getsize(test_filename) > 0:
                resultados['escritura_ok'] = True
                resultados['permisos']['escritura_archivo'] = True
                
                # Leer el archivo para probar lectura
                with open(test_filename, 'r') as f:
                    content = f.read()
                    resultados['permisos']['lectura_archivo'] = content == 'test_usb_permissions'
            else:
                resultados['permisos']['escritura_archivo'] = False
                
        except Exception as e:
            resultados['error_escritura'] = str(e)
            resultados['permisos']['escritura_archivo'] = False
        finally:
            # Limpiar archivo de prueba
            if test_filename and os.path.exists(test_filename):
                try:
                    os.unlink(test_filename)
                except:
                    pass
        
        # Probar creación de carpeta
        try:
            test_folder = os.path.join(usb_path, f'test_folder_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
            os.makedirs(test_folder, exist_ok=True)
            
            if os.path.exists(test_folder) and os.path.isdir(test_folder):
                resultados['carpeta_ok'] = True
                resultados['permisos']['creacion_carpeta'] = True
                
                # Probar escritura dentro de la carpeta
                test_inner_file = os.path.join(test_folder, 'inner_test.tmp')
                with open(test_inner_file, 'w') as f:
                    f.write('test')
                resultados['permisos']['escritura_carpeta'] = os.path.exists(test_inner_file)
                
                # Limpiar
                try:
                    if os.path.exists(test_inner_file):
                        os.remove(test_inner_file)
                    if os.path.exists(test_folder):
                        os.rmdir(test_folder)
                except:
                    pass
            else:
                resultados['permisos']['creacion_carpeta'] = False
                
        except Exception as e:
            resultados['error_carpeta'] = str(e)
            resultados['permisos']['creacion_carpeta'] = False
        
        # Verificar espacio disponible
        try:
            espacio = psutil.disk_usage(usb_path)
            resultados['espacio_libre_gb'] = round(espacio.free / (1024**3), 2)
            resultados['espacio_total_gb'] = round(espacio.total / (1024**3), 2)
            resultados['permisos']['lectura_espacio'] = True
        except Exception as e:
            resultados['error_espacio'] = str(e)
            resultados['permisos']['lectura_espacio'] = False
        
        return jsonify(resultados)
        
    except Exception as e:
        current_app.logger.error(f"Error en test_usb_permisos: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error testeando permisos USB'
        }), 500

# routes.py - CORREGIR ESTAS FUNCIONES

@backup_bp.route('/copiar-a-usb', methods=['POST'])
@login_required
def copiar_a_usb():
    """Copiar respaldos a unidad USB - VERSIÓN CORREGIDA"""
    try:
        # Verificación inicial
        if current_user.rol != 'admin':
            return jsonify({
                'success': False,
                'message': 'Acceso denegado. Solo administradores pueden copiar respaldos.'
            }), 403
        
        # IMPORTANTE: Verificar que la solicitud viene con JSON
        if not request.is_json:
            return jsonify({
                'success': False,
                'message': 'La solicitud debe ser JSON',
                'content_type': request.content_type
            }), 400
        
        # Obtener datos JSON
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'Datos JSON no válidos o vacíos'
            }), 400
        
        current_app.logger.info(f"Datos recibidos para copiar a USB: {data}")
        
        # Detectar USB
        usb_info = detectar_usb_json()
        current_app.logger.info(f"Intento de copia USB - Estado: {usb_info.get('conectado')}")
        
        if not usb_info.get('conectado'):
            return jsonify({
                'success': False,
                'message': 'No se detectó ninguna unidad USB conectada.',
                'conectado': False,
                'sugerencia': 'Conecta una unidad USB y haz clic en "Buscar USB nuevamente"'
            }), 400
        
        usb_path = usb_info['ruta']
        
        # Validar ruta segura
        if not validar_ruta_segura(usb_path):
            return jsonify({
                'success': False,
                'message': f'La ruta "{usb_path}" no es una unidad de almacenamiento válida.',
                'error_type': 'ruta_invalida'
            }), 400
        
        # Verificar espacio disponible
        try:
            espacio_usb = psutil.disk_usage(usb_path)
            espacio_libre_mb = espacio_usb.free / (1024**2)
            
            if espacio_libre_mb < 50:  # Menos de 50MB libres
                return jsonify({
                    'success': False,
                    'message': f'Espacio insuficiente en USB. Solo hay {round(espacio_libre_mb, 2)} MB libres.',
                    'espacio_libre_mb': round(espacio_libre_mb, 2),
                    'sugerencia': 'Libera espacio en el USB o usa otra unidad'
                }), 400
        except Exception as e:
            current_app.logger.warning(f"No se pudo verificar espacio USB: {e}")
        
        # Crear carpeta de respaldos
        try:
            usb_backup_folder = crear_backup_folder_usb(usb_path)
            
            # Verificar que la carpeta se creó
            if not os.path.exists(usb_backup_folder):
                return jsonify({
                    'success': False,
                    'message': f'No se pudo crear la carpeta de respaldos en {usb_backup_folder}',
                    'error_type': 'creacion_carpeta'
                }), 500
                
            # Probar escritura en la carpeta
            test_file = os.path.join(usb_backup_folder, '.test_permisos.tmp')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            
        except PermissionError as e:
            return jsonify({
                'success': False,
                'message': f'Sin permisos de escritura en el USB: {str(e)}',
                'error_type': 'permiso_denegado',
                'usb_path': usb_path
            }), 403
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error accediendo al USB: {str(e)}',
                'error_type': 'error_acceso_usb'
            }), 500
        
        # Procesar la copia
        copiar_todos = data.get('copiar_todos', False)
        respaldo_id = data.get('respaldo_id')
        
        if copiar_todos:
            return _copiar_todos_respaldos_usb(usb_backup_folder, current_user)
        elif respaldo_id:
            return _copiar_respaldo_especifico_usb(respaldo_id, usb_backup_folder, current_user)
        else:
            return jsonify({
                'success': False,
                'message': 'Debe especificar qué desea copiar.',
                'opciones': {
                    'copiar_todos': 'true - para copiar todos los respaldos locales',
                    'respaldo_id': 'ID - para copiar un respaldo específico'
                }
            }), 400
            
    except Exception as e:
        current_app.logger.error(f"Error en copiar_a_usb: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error interno al procesar la solicitud: {str(e)}',
            'error_type': 'error_interno',
            'trace': str(e)
        }), 500

def _copiar_todos_respaldos_usb(usb_backup_folder, usuario):
    """Función auxiliar para copiar todos los respaldos locales a USB"""
    try:
        # Obtener respaldos locales
        respaldos = Respaldo.query.filter_by(almacenamiento='local').all()
        
        if not respaldos:
            return jsonify({
                'success': True,
                'message': 'No hay respaldos locales para copiar.',
                'copiados': 0,
                'total': 0
            })
        
        copiados = []
        errores = []
        tamaño_total = 0
        
        for respaldo in respaldos:
            try:
                # Verificar archivo fuente
                if not respaldo.ruta_archivo or not os.path.exists(respaldo.ruta_archivo):
                    errores.append({
                        'id': respaldo.id,
                        'error': 'Archivo fuente no encontrado',
                        'ruta': respaldo.ruta_archivo
                    })
                    continue
                
                # Verificar que sea un archivo regular
                if not os.path.isfile(respaldo.ruta_archivo):
                    errores.append({
                        'id': respaldo.id,
                        'error': 'No es un archivo válido',
                        'ruta': respaldo.ruta_archivo
                    })
                    continue
                
                # Obtener información del archivo
                tamaño_archivo = os.path.getsize(respaldo.ruta_archivo)
                tamaño_total += tamaño_archivo
                
                # Generar nombre seguro para el destino
                nombre_base = os.path.basename(respaldo.ruta_archivo)
                nombre_seguro = secure_filename(nombre_base)
                
                # Si el archivo ya existe, agregar timestamp
                destino = os.path.join(usb_backup_folder, nombre_seguro)
                if os.path.exists(destino):
                    nombre_sin_ext, extension = os.path.splitext(nombre_seguro)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    nombre_seguro = f"{nombre_sin_ext}_{timestamp}{extension}"
                    destino = os.path.join(usb_backup_folder, nombre_seguro)
                
                # Copiar archivo
                current_app.logger.info(f"Copiando {respaldo.ruta_archivo} a {destino}")
                shutil.copy2(respaldo.ruta_archivo, destino)
                
                # Verificar que se copió correctamente
                if not os.path.exists(destino) or os.path.getsize(destino) != tamaño_archivo:
                    errores.append({
                        'id': respaldo.id,
                        'error': 'Error en la copia del archivo'
                    })
                    continue
                
                # Calcular checksum del archivo copiado
                checksum = calcular_checksum(destino)
                
                # Registrar en base de datos
                nuevo_respaldo = Respaldo(
                    tipo_respaldo=f"copia_usb_{respaldo.tipo_respaldo}",
                    ruta_archivo=destino,
                    tamaño_mb=round(tamaño_archivo / (1024 * 1024), 2),
                    realizado_por=usuario.nombre,
                    almacenamiento='usb',
                    checksum=checksum,
                    fecha_respaldo=datetime.utcnow()
                )
                db.session.add(nuevo_respaldo)
                
                copiados.append({
                    'id_original': respaldo.id,
                    'id_nuevo': nuevo_respaldo.id,
                    'archivo': nombre_seguro,
                    'tamaño_mb': round(tamaño_archivo / (1024 * 1024), 2),
                    'checksum': checksum[:16] + '...'
                })
                
            except Exception as e:
                errores.append({
                    'id': respaldo.id if respaldo else 'desconocido',
                    'error': str(e)
                })
                current_app.logger.error(f"Error copiando respaldo: {e}")
        
        # Guardar todos los cambios
        db.session.commit()
        
        # Preparar respuesta
        respuesta = {
            'success': True,
            'message': f'Proceso de copia completado. {len(copiados)} de {len(respaldos)} respaldos copiados.',
            'copiados': copiados,
            'errores': errores if errores else None,
            'total_respaldos': len(respaldos),
            'copiados_exitosos': len(copiados),
            'errores_total': len(errores),
            'tamaño_total_mb': round(tamaño_total / (1024 * 1024), 2),
            'carpeta_destino': usb_backup_folder
        }
        
        current_app.logger.info(f"Copia USB completada: {len(copiados)} exitosos, {len(errores)} errores")
        
        return jsonify(respuesta)
        
    except Exception as e:
        db.session.rollback()
        raise e

def _copiar_respaldo_especifico_usb(respaldo_id, usb_backup_folder, usuario):
    """Función auxiliar para copiar un respaldo específico a USB"""
    try:
        # Validar y obtener respaldo
        try:
            respaldo_id = int(respaldo_id)
        except ValueError:
            return jsonify({
                'success': False,
                'message': f'ID de respaldo inválido: {respaldo_id}',
                'error_type': 'id_invalido'
            }), 400
        
        respaldo = Respaldo.query.get(respaldo_id)
        
        if not respaldo:
            return jsonify({
                'success': False,
                'message': f'Respaldo #{respaldo_id} no encontrado',
                'error_type': 'respaldo_no_encontrado'
            }), 404
        
        if respaldo.almacenamiento != 'local':
            return jsonify({
                'success': False,
                'message': f'El respaldo #{respaldo_id} ya está almacenado en {respaldo.almacenamiento}',
                'error_type': 'ya_en_usb'
            }), 400
        
        # Verificar archivo fuente
        if not respaldo.ruta_archivo:
            return jsonify({
                'success': False,
                'message': f'El respaldo #{respaldo_id} no tiene ruta de archivo asignada',
                'error_type': 'sin_ruta_archivo'
            }), 400
        
        if not os.path.exists(respaldo.ruta_archivo):
            return jsonify({
                'success': False,
                'message': f'Archivo no encontrado: {respaldo.ruta_archivo}',
                'error_type': 'archivo_no_encontrado'
            }), 404
        
        if not os.path.isfile(respaldo.ruta_archivo):
            return jsonify({
                'success': False,
                'message': f'La ruta no es un archivo válido: {respaldo.ruta_archivo}',
                'error_type': 'no_es_archivo'
            }), 400
        
        # Obtener información del archivo
        tamaño_archivo = os.path.getsize(respaldo.ruta_archivo)
        nombre_base = os.path.basename(respaldo.ruta_archivo)
        
        # Generar nombre seguro
        nombre_seguro = secure_filename(nombre_base)
        
        # Si el archivo ya existe, agregar timestamp
        destino = os.path.join(usb_backup_folder, nombre_seguro)
        if os.path.exists(destino):
            nombre_sin_ext, extension = os.path.splitext(nombre_seguro)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            nombre_seguro = f"{nombre_sin_ext}_{timestamp}{extension}"
            destino = os.path.join(usb_backup_folder, nombre_seguro)
        
        # Copiar archivo
        current_app.logger.info(f"Copiando respaldo {respaldo_id} a {destino}")
        shutil.copy2(respaldo.ruta_archivo, destino)
        
        # Verificar copia
        if not os.path.exists(destino):
            return jsonify({
                'success': False,
                'message': 'Error: El archivo no se copió correctamente',
                'error_type': 'error_copia'
            }), 500
        
        if os.path.getsize(destino) != tamaño_archivo:
            return jsonify({
                'success': False,
                'message': f'Error: Tamaño del archivo copiado no coincide',
                'error_type': 'tamaño_invalido'
            }), 500
        
        # Calcular checksum
        checksum = calcular_checksum(destino)
        
        # Registrar en base de datos
        nuevo_respaldo = Respaldo(
            tipo_respaldo=f"copia_usb_{respaldo.tipo_respaldo}",
            ruta_archivo=destino,
            tamaño_mb=round(tamaño_archivo / (1024 * 1024), 2),
            realizado_por=usuario.nombre,
            almacenamiento='usb',
            checksum=checksum,
            fecha_respaldo=datetime.utcnow()
        )
        db.session.add(nuevo_respaldo)
        db.session.commit()
        
        # Registrar acción en historial
        historial = HistorialAcceso(
            usuario_id=usuario.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            estado_sesion='copia_usb',
            accion=f'copiar_respaldo_{respaldo_id}_a_usb'
        )
        db.session.add(historial)
        db.session.commit()
        
        # Preparar respuesta detallada
        respuesta = {
            'success': True,
            'message': f'✅ Respaldo #{respaldo_id} copiado exitosamente a USB',
            'detalles': {
                'respaldo_original': {
                    'id': respaldo.id,
                    'tipo': respaldo.tipo_respaldo,
                    'tamaño_mb': respaldo.tamaño_mb
                },
                'copia_usb': {
                    'id': nuevo_respaldo.id,
                    'archivo': nombre_seguro,
                    'tamaño_mb': round(tamaño_archivo / (1024 * 1024), 2),
                    'checksum': checksum[:16] + '...'
                },
                'ubicacion': {
                    'carpeta_usb': usb_backup_folder
                }
            }
        }
        
        current_app.logger.info(f"Respaldo {respaldo_id} copiado exitosamente a USB")
        
        return jsonify(respuesta)
        
    except Exception as e:
        db.session.rollback()
        raise e

@backup_bp.route('/debug-usb-detection')
@login_required
def debug_usb_detection():
    """Página de debug para verificar detección USB"""
    if current_user.rol != 'admin':
        return jsonify({'error': 'Acceso no autorizado'}), 403
    
    import subprocess
    
    info = {
        'sistema': platform.system(),
        'python_version': platform.python_version(),
        'directorio_actual': os.getcwd(),
        'usuario_os': os.getenv('USER') or os.getenv('USERNAME'),
        'particiones': [],
        'proceso_deteccion': {}
    }
    
    # Información de particiones usando psutil
    for particion in psutil.disk_partitions():
        try:
            uso = psutil.disk_usage(particion.mountpoint)
            info['particiones'].append({
                'dispositivo': particion.device,
                'punto_montaje': particion.mountpoint,
                'tipo': particion.fstype,
                'opciones': particion.opts,
                'espacio_total_gb': round(uso.total / (1024**3), 2),
                'espacio_usado_gb': round(uso.used / (1024**3), 2),
                'espacio_libre_gb': round(uso.free / (1024**3), 2),
                'porcentaje_usado': uso.percent
            })
        except Exception as e:
            info['particiones'].append({
                'dispositivo': particion.device,
                'punto_montaje': particion.mountpoint,
                'error': str(e)
            })
    
    # Ejecutar función de detección
    info['proceso_deteccion'] = detectar_usb_json()
    
    # Comandos del sistema
    if platform.system() == 'Windows':
        try:
            result = subprocess.run(['wmic', 'logicaldisk', 'get', 'caption,drivetype,size,freespace'], 
                                  capture_output=True, text=True, timeout=5)
            info['comando_wmic'] = result.stdout
        except:
            info['comando_wmic'] = 'No disponible'
    elif platform.system() == 'Linux':
        try:
            result = subprocess.run(['lsblk', '-o', 'NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE'], 
                                  capture_output=True, text=True, timeout=5)
            info['comando_lsblk'] = result.stdout
        except:
            info['comando_lsblk'] = 'No disponible'
    
    return jsonify(info)

@backup_bp.route('/verificar-todos')
@login_required
def verificar_todos():
    """Verificar integridad de todos los respaldos"""
    try:
        if current_user.rol != 'admin':
            return jsonify({'success': False, 'message': 'No autorizado'}), 403
        
        respaldos = Respaldo.query.order_by(Respaldo.fecha_respaldo.desc()).all()
        
        if not respaldos:
            return jsonify({
                'success': True,
                'message': 'No hay respaldos para verificar',
                'total': 0,
                'verificados': 0,
                'errores': 0
            })
        
        resultados = {
            'success': True,
            'total': len(respaldos),
            'verificados': [],
            'errores': [],
            'resumen': {
                'total_bytes': 0,
                'total_mb': 0,
                'por_almacenamiento': {},
                'por_tipo': {}
            }
        }
        
        for respaldo in respaldos:
            item = {
                'id': respaldo.id,
                'tipo': respaldo.tipo_respaldo,
                'almacenamiento': respaldo.almacenamiento,
                'archivo': os.path.basename(respaldo.ruta_archivo) if respaldo.ruta_archivo else 'N/A',
                'fecha': respaldo.fecha_respaldo.isoformat() if respaldo.fecha_respaldo else None,
                'tamaño_mb': respaldo.tamaño_mb
            }
            
            try:
                if not respaldo.checksum:
                    item['estado'] = 'sin_checksum'
                    item['error'] = 'No tiene checksum registrado'
                    resultados['errores'].append(item)
                elif not respaldo.ruta_archivo:
                    item['estado'] = 'sin_ruta'
                    item['error'] = 'No tiene ruta de archivo'
                    resultados['errores'].append(item)
                elif not os.path.exists(respaldo.ruta_archivo):
                    item['estado'] = 'archivo_no_encontrado'
                    item['error'] = f'Archivo no encontrado: {respaldo.ruta_archivo}'
                    resultados['errores'].append(item)
                else:
                    # Verificar si es un archivo válido
                    if not os.path.isfile(respaldo.ruta_archivo):
                        item['estado'] = 'no_es_archivo'
                        item['error'] = 'La ruta no es un archivo válido'
                        resultados['errores'].append(item)
                        continue
                    
                    # Calcular checksum actual
                    checksum_actual = calcular_checksum(respaldo.ruta_archivo)
                    tamaño_actual = os.path.getsize(respaldo.ruta_archivo)
                    
                    if checksum_actual == respaldo.checksum:
                        item['estado'] = 'verificado'
                        item['checksum_coincide'] = True
                        item['tamaño_bytes'] = tamaño_actual
                        item['tamaño_mb_actual'] = round(tamaño_actual / (1024 * 1024), 2)
                        resultados['verificados'].append(item)
                        
                        # Actualizar resumen
                        resultados['resumen']['total_bytes'] += tamaño_actual
                        resultados['resumen']['total_mb'] += item['tamaño_mb_actual']
                        
                        # Contar por almacenamiento
                        almac = respaldo.almacenamiento
                        resultados['resumen']['por_almacenamiento'][almac] = resultados['resumen']['por_almacenamiento'].get(almac, 0) + 1
                        
                        # Contar por tipo
                        tipo = respaldo.tipo_respaldo
                        resultados['resumen']['por_tipo'][tipo] = resultados['resumen']['por_tipo'].get(tipo, 0) + 1
                        
                    else:
                        item['estado'] = 'checksum_no_coincide'
                        item['error'] = f'Checksum no coincide. Esperado: {respaldo.checksum[:16]}..., Actual: {checksum_actual[:16]}...'
                        item['checksum_esperado'] = respaldo.checksum[:16] + '...'
                        item['checksum_actual'] = checksum_actual[:16] + '...'
                        resultados['errores'].append(item)
                        
            except Exception as e:
                item['estado'] = 'error_verificacion'
                item['error'] = str(e)
                resultados['errores'].append(item)
        
        # Calcular porcentajes
        resultados['verificados_count'] = len(resultados['verificados'])
        resultados['errores_count'] = len(resultados['errores'])
        resultados['porcentaje_exito'] = round((resultados['verificados_count'] / resultados['total']) * 100, 2) if resultados['total'] > 0 else 0
        
        # Redondear valores
        resultados['resumen']['total_mb'] = round(resultados['resumen']['total_mb'], 2)
        resultados['resumen']['total_gb'] = round(resultados['resumen']['total_mb'] / 1024, 2)
        
        return jsonify(resultados)
        
    except Exception as e:
        current_app.logger.error(f"Error en verificar_todos: {e}")
        return jsonify({
            'success': False,
            'message': f'Error al verificar respaldos: {str(e)}',
            'error_type': 'error_verificacion'
        }), 500

# ========== RUTAS DE RESPALDOS ==========
@backup_bp.route('/')
@login_required
def listar_respaldos():
    """Listar todos los respaldos disponibles - VERSIÓN MEJORADA"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden acceder a esta sección', 'danger')
        return redirect(url_for('main.dashboard'))
    
    respaldos = Respaldo.query.order_by(Respaldo.fecha_respaldo.desc()).all()
    
    # Detectar USB con información detallada
    usb_info = detectar_usb_json()
    
    # Pasar información clara al template
    usb_mounted = usb_info.get('conectado', False)
    usb_path = usb_info.get('ruta', 'No detectado')
    usb_free_space = usb_info.get('espacio_libre', 0)
    usb_total_space = usb_info.get('espacio_total', 0)
    
    # Estadísticas por tipo
    total_completos = Respaldo.query.filter_by(tipo_respaldo='completo').count()
    total_diferenciales = Respaldo.query.filter_by(tipo_respaldo='diferencial').count()
    total_copias_usb = Respaldo.query.filter(Respaldo.tipo_respaldo.like('copia_usb_%')).count()
    total_importados = Respaldo.query.filter(Respaldo.tipo_respaldo.like('importado_%')).count()
    
    last_backup_time = 'Nunca'
    if respaldos and respaldos[0] and respaldos[0].fecha_respaldo:
        try:
            last_backup = respaldos[0].fecha_respaldo
            now = datetime.utcnow()
            diff = now - last_backup
            
            if diff.days > 0:
                if diff.days == 1:
                    last_backup_time = 'Ayer'
                else:
                    last_backup_time = f'Hace {diff.days} días'
            elif diff.seconds >= 3600:
                horas = diff.seconds // 3600
                last_backup_time = f'Hace {horas} hora{"s" if horas > 1 else ""}'
            elif diff.seconds >= 60:
                minutos = diff.seconds // 60
                last_backup_time = f'Hace {minutos} minuto{"s" if minutos > 1 else ""}'
            else:
                last_backup_time = 'Hace unos momentos'
        except Exception as e:
            current_app.logger.error(f"Error calculando tiempo: {e}")
            last_backup_time = 'N/A'
    
    return render_template('backups/lista.html', 
                         respaldos=respaldos,
                         total_completos=total_completos,
                         total_diferenciales=total_diferenciales,
                         total_copias_usb=total_copias_usb,
                         total_importados=total_importados,
                         usb_mounted=usb_mounted,
                         usb_path=usb_path,
                         usb_free_space=usb_free_space,
                         usb_total_space=usb_total_space,
                         last_backup_time=last_backup_time)

@backup_bp.route('/crear/completo', methods=['POST'])
@login_required
def crear_respaldo_completo():
    """Crear un respaldo completo de la base de datos"""
    if current_user.rol != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        almacenamiento = request.form.get('almacenamiento', 'local')
        
        if almacenamiento == 'usb':
            usb_info = detectar_usb_json()
            if not usb_info.get('conectado'):
                return jsonify({
                    'success': False, 
                    'message': 'No hay unidad USB disponible'
                }), 400
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"respaldo_completo_{timestamp}.sql.gz"
        
        if almacenamiento == 'usb':
            usb_info = detectar_usb_json()
            if not usb_info.get('conectado'):
                return jsonify({
                    'success': False, 
                    'message': 'Error al acceder al USB'
                }), 400
            
            usb_backup_folder = crear_backup_folder_usb(usb_info['ruta'])
            filepath = os.path.join(usb_backup_folder, filename)
        else:
            filepath = os.path.join(BACKUP_FOLDER, filename)
        
        # Obtener configuración de la base de datos
        db_config = current_app.config
        
        # Crear archivo temporal
        temp_file = os.path.join(BACKUP_FOLDER, f"temp_{timestamp}.sql")
        
        # Construir comando mysqldump
        db_host = db_config.get('MYSQL_HOST', 'localhost')
        db_user = db_config.get('MYSQL_USER', 'root')
        db_password = db_config.get('MYSQL_PASSWORD', '')
        db_name = db_config.get('MYSQL_DATABASE', 'gestion_plantas')
        
        # Crear comando seguro
        if db_password:
            cmd = ['mysqldump', '-h', db_host, '-u', db_user, f'-p{db_password}', db_name]
        else:
            cmd = ['mysqldump', '-h', db_host, '-u', db_user, db_name]
        
        # Ejecutar comando
        try:
            with open(temp_file, 'w') as f:
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                return jsonify({
                    'success': False,
                    'message': f'Error al crear respaldo: {result.stderr[:200]}'
                }), 500
        except Exception as e:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            return jsonify({
                'success': False,
                'message': f'Error al ejecutar mysqldump: {str(e)}'
            }), 500
        
        # Comprimir archivo
        try:
            with open(temp_file, 'rb') as f_in:
                with gzip.open(filepath, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        except Exception as e:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({
                'success': False,
                'message': f'Error al comprimir archivo: {str(e)}'
            }), 500
        
        # Eliminar archivo temporal
        if os.path.exists(temp_file):
            os.remove(temp_file)
        
        # Calcular tamaño y checksum
        tamaño_mb = os.path.getsize(filepath) / (1024 * 1024)
        checksum = calcular_checksum(filepath)
        
        # GUARDAR EN BASE DE DATOS - RESPLADO COMPLETO
        nuevo_respaldo = Respaldo(
            tipo_respaldo='completo',
            ruta_archivo=filepath,
            tamaño_mb=round(tamaño_mb, 2),
            realizado_por=current_user.nombre,
            almacenamiento=almacenamiento,
            checksum=checksum,
            fecha_respaldo=datetime.utcnow()
        )
        
        db.session.add(nuevo_respaldo)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'✅ Respaldo completo creado exitosamente ({tamaño_mb:.2f} MB)',
            'respaldo_id': nuevo_respaldo.id,
            'tipo': 'completo',
            'tamaño': round(tamaño_mb, 2),
            'fecha': nuevo_respaldo.fecha_respaldo.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        db.session.rollback()
        if 'temp_file' in locals() and os.path.exists(temp_file):
            os.remove(temp_file)
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)
        
        current_app.logger.error(f"Error al crear respaldo completo: {e}")
        return jsonify({
            'success': False,
            'message': f'❌ Error al crear respaldo: {str(e)}'
        }), 500

@backup_bp.route('/crear/diferencial', methods=['POST'])
@login_required
def crear_respaldo_diferencial():
    """Crear un respaldo diferencial"""
    if current_user.rol != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        almacenamiento = request.form.get('almacenamiento', 'local')
        
        # Buscar último respaldo completo
        ultimo_completo = Respaldo.query.filter_by(tipo_respaldo='completo')\
            .order_by(Respaldo.fecha_respaldo.desc())\
            .first()
        
        if not ultimo_completo:
            return jsonify({
                'success': False,
                'message': '❌ Primero debes crear un respaldo completo'
            }), 400
        
        if almacenamiento == 'usb':
            usb_info = detectar_usb_json()
            if not usb_info.get('conectado'):
                return jsonify({
                    'success': False, 
                    'message': 'No hay unidad USB disponible'
                }), 400
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"respaldo_diferencial_{timestamp}.sql.gz"
        
        if almacenamiento == 'usb':
            usb_info = detectar_usb_json()
            usb_backup_folder = crear_backup_folder_usb(usb_info['ruta'])
            filepath = os.path.join(usb_backup_folder, filename)
        else:
            filepath = os.path.join(BACKUP_FOLDER, filename)
        
        # Configuración de base de datos
        db_config = current_app.config
        db_host = db_config.get('MYSQL_HOST', 'localhost')
        db_user = db_config.get('MYSQL_USER', 'root')
        db_password = db_config.get('MYSQL_PASSWORD', '')
        db_name = db_config.get('MYSQL_DATABASE', 'gestion_plantas')
        
        temp_file = os.path.join(BACKUP_FOLDER, f"temp_dif_{timestamp}.sql")
        
        # Tablas que queremos respaldar diferencialmente
        tablas_transaccionales = ['plantas', 'registros_riego', 'pedidos', 'pedido_detalle', 'historial_accesos']
        
        # Crear archivo SQL con datos nuevos
        fecha_ultimo_completo = ultimo_completo.fecha_respaldo.strftime('%Y-%m-%d %H:%M:%S')
        
        with open(temp_file, 'w') as f:
            for tabla in tablas_transaccionales:
                try:
                    # Construir comando para respaldar solo datos nuevos
                    if db_password:
                        cmd_base = ['mysqldump', '-h', db_host, '-u', db_user, f'-p{db_password}', db_name, tabla, '--no-create-info']
                    else:
                        cmd_base = ['mysqldump', '-h', db_host, '-u', db_user, db_name, tabla, '--no-create-info']
                    
                    # Intentar con diferentes campos de fecha
                    campos_fecha = ['fecha_registro', 'fecha_creacion', 'fecha_orden', 'fecha_acceso', 'fecha_riego']
                    
                    for campo in campos_fecha:
                        try:
                            cmd = cmd_base + ['--where', f'{campo} > "{fecha_ultimo_completo}"']
                            result = subprocess.run(cmd, capture_output=True, text=True)
                            if result.returncode == 0 and result.stdout.strip():
                                f.write(result.stdout)
                                f.write("\n")
                                break
                        except:
                            continue
                            
                except Exception as e:
                    current_app.logger.error(f"Error respaldando tabla {tabla}: {e}")
                    continue
        
        # Verificar si hay datos nuevos
        if os.path.exists(temp_file) and os.path.getsize(temp_file) < 100:
            os.remove(temp_file)
            return jsonify({
                'success': True,
                'message': '✅ No hay cambios desde el último respaldo completo'
            })
        
        # Comprimir archivo
        with open(temp_file, 'rb') as f_in:
            with gzip.open(filepath, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        os.remove(temp_file)
        
        # Calcular tamaño y checksum
        tamaño_mb = os.path.getsize(filepath) / (1024 * 1024)
        checksum = calcular_checksum(filepath)
        
        # GUARDAR EN BASE DE DATOS - RESPALDO DIFERENCIAL
        nuevo_respaldo = Respaldo(
            tipo_respaldo='diferencial',
            ruta_archivo=filepath,
            tamaño_mb=round(tamaño_mb, 2),
            realizado_por=current_user.nombre,
            almacenamiento=almacenamiento,
            checksum=checksum,
            fecha_respaldo=datetime.utcnow()
        )
        
        db.session.add(nuevo_respaldo)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'✅ Respaldo diferencial creado exitosamente ({tamaño_mb:.2f} MB)',
            'respaldo_id': nuevo_respaldo.id,
            'tipo': 'diferencial',
            'tamaño': round(tamaño_mb, 2),
            'fecha': nuevo_respaldo.fecha_respaldo.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        db.session.rollback()
        if 'temp_file' in locals() and os.path.exists(temp_file):
            os.remove(temp_file)
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)
        
        current_app.logger.error(f"Error al crear respaldo diferencial: {e}")
        return jsonify({
            'success': False,
            'message': f'❌ Error al crear respaldo diferencial: {str(e)}'
        }), 500

@backup_bp.route('/restaurar/<int:id>', methods=['POST'])
@login_required
def restaurar_respaldo(id):
    """Restaurar base de datos desde un respaldo"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden restaurar respaldos', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    respaldo = Respaldo.query.get_or_404(id)
    
    try:
        if not os.path.exists(respaldo.ruta_archivo):
            flash('❌ El archivo de respaldo no existe', 'danger')
            return redirect(url_for('backup.listar_respaldos'))
        
        # Verificar integridad del respaldo
        checksum_actual = calcular_checksum(respaldo.ruta_archivo)
        if respaldo.checksum and checksum_actual != respaldo.checksum:
            flash('⚠️ Advertencia: El checksum no coincide. El archivo puede estar corrupto.', 'warning')
        
        # Obtener configuración de la base de datos
        db_config = current_app.config
        db_host = db_config.get('MYSQL_HOST', 'localhost')
        db_user = db_config.get('MYSQL_USER', 'root')
        db_password = db_config.get('MYSQL_PASSWORD', '')
        db_name = db_config.get('MYSQL_DATABASE', 'gestion_plantas')
        
        # Registrar intento de restauración en el historial
        historial_restauracion = HistorialAcceso(
            usuario_id=current_user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            estado_sesion='restauracion',
            accion=f'restaurar_respaldo_{id}'
        )
        db.session.add(historial_restauracion)
        
        if respaldo.ruta_archivo.endswith('.gz'):
            temp_file = os.path.join(BACKUP_FOLDER, f"temp_restore_{id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql")
            
            with gzip.open(respaldo.ruta_archivo, 'rb') as f_in:
                with open(temp_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Crear comando seguro
            if db_password:
                cmd = ['mysql', '-h', db_host, '-u', db_user, f'-p{db_password}', db_name]
            else:
                cmd = ['mysql', '-h', db_host, '-u', db_user, db_name]
            
            # Ejecutar comando
            try:
                with open(temp_file, 'r') as f:
                    result = subprocess.run(cmd, stdin=f, capture_output=True, text=True)
                
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                flash(f'❌ Error al restaurar: {str(e)}', 'danger')
                db.session.commit()
                return redirect(url_for('backup.listar_respaldos'))
        else:
            # Crear comando seguro
            if db_password:
                cmd = ['mysql', '-h', db_host, '-u', db_user, f'-p{db_password}', db_name]
            else:
                cmd = ['mysql', '-h', db_host, '-u', db_user, db_name]
            
            # Ejecutar comando
            try:
                with open(respaldo.ruta_archivo, 'r') as f:
                    result = subprocess.run(cmd, stdin=f, capture_output=True, text=True)
            except Exception as e:
                flash(f'❌ Error al restaurar: {str(e)}', 'danger')
                db.session.commit()
                return redirect(url_for('backup.listar_respaldos'))
        
        if result.returncode != 0:
            flash(f'❌ Error al restaurar: {result.stderr[:200]}', 'danger')
        else:
            flash('✅ Base de datos restaurada exitosamente', 'success')
        
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error al restaurar respaldo: {str(e)}', 'danger')
    
    return redirect(url_for('backup.listar_respaldos'))

@backup_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_respaldo(id):
    """Eliminar un respaldo"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden eliminar respaldos', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    respaldo = Respaldo.query.get_or_404(id)
    
    try:
        # Intentar eliminar el archivo físico
        if os.path.exists(respaldo.ruta_archivo):
            try:
                os.remove(respaldo.ruta_archivo)
            except Exception as e:
                flash(f'⚠️ No se pudo eliminar el archivo físico: {str(e)}', 'warning')
        
        # Registrar eliminación en el historial
        historial_eliminacion = HistorialAcceso(
            usuario_id=current_user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            estado_sesion='eliminacion',
            accion=f'eliminar_respaldo_{id}'
        )
        db.session.add(historial_eliminacion)
        
        # Eliminar registro de la base de datos
        db.session.delete(respaldo)
        db.session.commit()
        
        flash('✅ Respaldo eliminado exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error al eliminar respaldo: {str(e)}', 'danger')
    
    return redirect(url_for('backup.listar_respaldos'))

@backup_bp.route('/verificar/<int:id>')
@login_required
def verificar_respaldo(id):
    """Verificar integridad de un respaldo"""
    if current_user.rol != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    respaldo = Respaldo.query.get_or_404(id)
    
    try:
        if not os.path.exists(respaldo.ruta_archivo):
            return jsonify({
                'estado': 'error',
                'mensaje': 'Archivo no encontrado'
            })
        
        checksum_actual = calcular_checksum(respaldo.ruta_archivo)
        integridad = checksum_actual == respaldo.checksum
        
        return jsonify({
            'estado': 'ok',
            'id': respaldo.id,
            'archivo': os.path.basename(respaldo.ruta_archivo),
            'tipo_respaldo': respaldo.tipo_respaldo,
            'checksum_original': respaldo.checksum,
            'checksum_actual': checksum_actual,
            'integridad': integridad,
            'tamaño_mb': respaldo.tamaño_mb if respaldo.tamaño_mb else 0,
            'fecha_creacion': respaldo.fecha_respaldo.strftime('%Y-%m-%d %H:%M:%S') if respaldo.fecha_respaldo else 'N/A',
            'almacenamiento': respaldo.almacenamiento,
            'realizado_por': respaldo.realizado_por
        })
        
    except Exception as e:
        return jsonify({
            'estado': 'error',
            'mensaje': str(e)
        })

@backup_bp.route('/descargar/<int:id>')
@login_required
def descargar_respaldo(id):
    """Descargar archivo de respaldo"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden descargar respaldos', 'danger')
        return redirect(url_for('main.dashboard'))
    
    respaldo = Respaldo.query.get_or_404(id)
    
    if not os.path.exists(respaldo.ruta_archivo):
        flash('Archivo no encontrado', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    # Registrar descarga en el historial
    historial_descarga = HistorialAcceso(
        usuario_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        estado_sesion='descarga',
        accion=f'descargar_respaldo_{id}'
    )
    db.session.add(historial_descarga)
    db.session.commit()
    
    return send_file(
        respaldo.ruta_archivo,
        as_attachment=True,
        download_name=os.path.basename(respaldo.ruta_archivo)
    )

@backup_bp.route('/importar', methods=['POST'])
@login_required
def importar_respaldo():
    """Importar respaldo desde archivo"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden importar respaldos', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    if 'archivo_respaldo' not in request.files:
        flash('No se seleccionó ningún archivo', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    file = request.files['archivo_respaldo']
    tipo_importacion = request.form.get('tipo_importacion', 'completo')
    almacenamiento = request.form.get('almacenamiento', 'local')
    
    if file.filename == '':
        flash('Nombre de archivo vacío', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            temp_path = os.path.join(BACKUP_FOLDER, filename)
            file.save(temp_path)
            
            # Configuración de base de datos
            db_config = current_app.config
            db_host = db_config.get('MYSQL_HOST', 'localhost')
            db_user = db_config.get('MYSQL_USER', 'root')
            db_password = db_config.get('MYSQL_PASSWORD', '')
            db_name = db_config.get('MYSQL_DATABASE', 'gestion_plantas')
            
            # Restaurar base de datos
            if filename.endswith('.gz'):
                import_file = temp_path.replace('.gz', '')
                with gzip.open(temp_path, 'rb') as f_in:
                    with open(import_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                # Crear comando seguro
                if db_password:
                    cmd = ['mysql', '-h', db_host, '-u', db_user, f'-p{db_password}', db_name]
                else:
                    cmd = ['mysql', '-h', db_host, '-u', db_user, db_name]
                
                # Ejecutar comando
                with open(import_file, 'r') as f:
                    result = subprocess.run(cmd, stdin=f, capture_output=True, text=True)
                
                os.remove(import_file)
            else:
                # Crear comando seguro
                if db_password:
                    cmd = ['mysql', '-h', db_host, '-u', db_user, f'-p{db_password}', db_name]
                else:
                    cmd = ['mysql', '-h', db_host, '-u', db_user, db_name]
                
                # Ejecutar comando
                with open(temp_path, 'r') as f:
                    result = subprocess.run(cmd, stdin=f, capture_output=True, text=True)
                
                os.remove(temp_path)
            
            if result.returncode != 0:
                flash('❌ Error al importar el respaldo. Verifica el formato del archivo.', 'danger')
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return redirect(url_for('backup.listar_respaldos'))
            
            # Calcular checksum y tamaño
            checksum = calcular_checksum(temp_path)
            tamaño_mb = os.path.getsize(temp_path) / (1024 * 1024) if os.path.exists(temp_path) else 0
            
            # GUARDAR EN BASE DE DATOS - RESPLADO IMPORTADO
            nuevo_respaldo = Respaldo(
                tipo_respaldo=f"importado_{tipo_importacion}",
                ruta_archivo=temp_path,
                tamaño_mb=round(tamaño_mb, 2),
                realizado_por=current_user.nombre,
                almacenamiento=almacenamiento,
                checksum=checksum,
                fecha_respaldo=datetime.utcnow()
            )
            
            # Registrar importación en el historial
            historial_importacion = HistorialAcceso(
                usuario_id=current_user.id,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string,
                estado_sesion='importacion',
                accion=f'importar_respaldo_{filename}'
            )
            
            db.session.add(nuevo_respaldo)
            db.session.add(historial_importacion)
            db.session.commit()
            
            flash('✅ Respaldo importado y restaurado exitosamente', 'success')
            
        except Exception as e:
            db.session.rollback()
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.remove(temp_path)
            flash(f'❌ Error al importar respaldo: {str(e)}', 'danger')
    else:
        flash('❌ Tipo de archivo no permitido. Use .sql o .gz', 'danger')
    
    return redirect(url_for('backup.listar_respaldos'))

# ========== AUTH ROUTES ==========
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.rol == 'admin':
            return redirect(url_for('main.dashboard'))
        elif current_user.rol == 'cliente':
            return redirect(url_for('tienda.tienda_index'))
        else:
            return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        correo = request.form.get('correo')
        contrasenia = request.form.get('contrasenia')
        
        usuario = Usuario.query.filter_by(correo=correo).first()
        
        if usuario:
            from werkzeug.security import check_password_hash
            if check_password_hash(usuario.contrasenia_hash, contrasenia):
                login_user(usuario, remember=True)
                
                acceso = HistorialAcceso(
                    usuario_id=usuario.id,
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string,
                    estado_sesion='iniciada',
                    accion='login'
                )
                db.session.add(acceso)
                db.session.commit()
                
                flash(f'¡Bienvenido, {usuario.nombre}!', 'success')
                
                if usuario.rol == 'admin':
                    return redirect(url_for('main.dashboard'))
                elif usuario.rol == 'cliente':
                    return redirect(url_for('tienda.tienda_index'))
                else:
                    return redirect(url_for('main.dashboard'))
            else:
                flash('Contraseña incorrecta', 'danger')
        else:
            flash('Usuario no encontrado', 'danger')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    acceso = HistorialAcceso(
        usuario_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        estado_sesion='cerrada',
        accion='logout'
    )
    db.session.add(acceso)
    db.session.commit()
    
    logout_user()
    flash('Has cerrado sesión', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/registro', methods=['GET', 'POST'])
def registro_cliente():
    """Registro de nuevos clientes"""
    if current_user.is_authenticated:
        if current_user.rol == 'cliente':
            return redirect(url_for('tienda.tienda_index'))
        else:
            return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        try:
            nombre = request.form.get('nombre', '').strip()
            correo = request.form.get('correo', '').strip().lower()
            contrasenia = request.form.get('contrasenia', '')
            confirmar_contrasenia = request.form.get('confirmar_contrasenia', '')
            telefono = request.form.get('telefono', '').strip()
            direccion = request.form.get('direccion', '').strip()
            
            errores = []
            
            if not nombre or len(nombre) < 3:
                errores.append('El nombre debe tener al menos 3 caracteres.')
            
            if not correo or '@' not in correo:
                errores.append('Correo electrónico inválido.')
            
            usuario_existente = Usuario.query.filter_by(correo=correo).first()
            if usuario_existente:
                errores.append('Este correo ya está registrado.')
            
            if not contrasenia or len(contrasenia) < 6:
                errores.append('La contraseña debe tener al menos 6 caracteres.')
            
            if contrasenia != confirmar_contrasenia:
                errores.append('Las contraseñas no coinciden.')
            
            if errores:
                for error in errores:
                    flash(error, 'danger')
                return render_template('auth/registro.html',
                                     nombre=nombre,
                                     correo=correo,
                                     telefono=telefono,
                                     direccion=direccion)
            
            from werkzeug.security import generate_password_hash
            
            nuevo_cliente = Usuario(
                nombre=nombre,
                correo=correo,
                contrasenia_hash=generate_password_hash(contrasenia),
                rol='cliente',
                telefono=telefono,
                direccion=direccion,
                fecha_registro=datetime.utcnow(),
                estado='activo'
            )
            
            db.session.add(nuevo_cliente)
            db.session.commit()
            
            acceso = HistorialAcceso(
                usuario_id=nuevo_cliente.id,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string,
                estado_sesion='registro',
                accion='registro_cliente'
            )
            db.session.add(acceso)
            db.session.commit()
            
            login_user(nuevo_cliente, remember=True)
            
            flash('¡Registro exitoso! Bienvenido/a a nuestra tienda.', 'success')
            return redirect(url_for('tienda.tienda_index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error en el registro: {str(e)}', 'danger')
            return render_template('auth/registro.html')
    
    return render_template('auth/registro.html')

# ========== MAIN ROUTES ==========
@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.rol == 'cliente':
        return redirect(url_for('tienda.tienda_index'))
    
    total_plantas = Planta.query.count()
    plantas_activas = Planta.query.filter_by(estado='activa').count()
    
    ultimos_riegos = RegistroRiego.query.join(Planta)\
        .order_by(RegistroRiego.fecha_riego.desc())\
        .limit(10)\
        .all()
    
    ultimo_backup = Respaldo.query.order_by(Respaldo.fecha_respaldo.desc()).first()
    ultimo_backup_fecha = ultimo_backup.fecha_respaldo if ultimo_backup else None
    
    return render_template('dashboard.html',
                         total_plantas=total_plantas,
                         plantas_riego_hoy=plantas_activas,
                         ultimos_riegos=ultimos_riegos,
                         ultimo_backup=ultimo_backup_fecha)

# ========== PLANTAS ROUTES ==========
@plants_bp.route('/')
@login_required
def listar_plantas():
    if current_user.rol == 'cliente':
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('tienda.tienda_index'))
    
    if current_user.rol == 'admin':
        plantas = Planta.query.all()
    else:
        plantas = Planta.query.filter_by(usuario_id=current_user.id).all()
    
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
            especie = request.form.get('especie', '').strip()
            precio = request.form.get('precio', 0.0)
            stock = request.form.get('stock', 0)
            categoria = request.form.get('categoria', '')
            descripcion = request.form.get('descripcion', '')
            
            if not nombre:
                flash('El nombre de la planta es requerido', 'error')
                return render_template('plants/crear.html')
            
            nueva_planta = Planta(
                nombre=nombre,
                especie=especie,
                precio=float(precio),
                stock=int(stock),
                categoria=categoria,
                descripcion=descripcion,
                estado='activa',
                usuario_id=current_user.id,
            )
            
            db.session.add(nueva_planta)
            db.session.commit()
            
            flash(f'¡Planta "{nombre}" creada exitosamente!', 'success')
            return redirect(url_for('plants.listar_plantas'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear la planta: {str(e)}', 'error')
            return render_template('plants/crear.html')
    
    return render_template('plants/crear.html')

@plants_bp.route('/<int:id>')
@login_required
def detalle_planta(id):
    planta = Planta.query.get_or_404(id)
    
    if current_user.rol == 'cliente':
        if not planta.disponible_venta or planta.estado != 'activa':
            flash('Planta no disponible', 'danger')
            return redirect(url_for('tienda.tienda_index'))
        return redirect(url_for('tienda.ver_planta_tienda', id=id))
    
    if current_user.rol != 'admin' and planta.usuario_id != current_user.id:
        flash('No tienes permiso para ver esta planta', 'danger')
        return redirect(url_for('plants.listar_plantas'))
    
    now = datetime.utcnow()
    return render_template('plants/detalle.html', planta=planta, now=now)

@plants_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_planta(id):
    if current_user.rol == 'cliente':
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('tienda.tienda_index'))
    
    planta = Planta.query.get_or_404(id)
    
    if current_user.rol != 'admin' and planta.usuario_id != current_user.id:
        flash('No tienes permiso para editar esta planta', 'danger')
        return redirect(url_for('plants.listar_plantas'))
    
    if request.method == 'POST':
        try:
            # Campos básicos (mantén los que ya tienes)
            planta.nombre = request.form.get('nombre', '').strip()
            planta.especie = request.form.get('especie', '').strip()
            planta.estado = request.form.get('estado', 'activa')
            planta.precio = float(request.form.get('precio', 0.0))
            planta.stock = int(request.form.get('stock', 0))
            planta.categoria = request.form.get('categoria', '')
            planta.descripcion = request.form.get('descripcion', '')
            planta.disponible_venta = bool(request.form.get('disponible_venta', False))
            
            # ========== MANEJO DE IMÁGENES MEJORADO ==========
            imagen_file = request.files.get('imagen')
            imagen_url = request.form.get('imagen_url', '').strip()
            eliminar_imagen = request.form.get('eliminar_imagen', False)
            
            # Si se marca para eliminar imagen
            if eliminar_imagen:
                if planta.es_imagen_local():
                    planta.eliminar_imagen_local(current_app)
                planta.imagen_url = None
                planta.imagen_nombre = None
                planta.imagen_path = None
            
            # Si se sube archivo
            elif imagen_file and imagen_file.filename:
                if allowed_image_file(imagen_file.filename):
                    # Guardar imagen localmente
                    filename = guardar_imagen(imagen_file, planta.id)
                    planta.actualizar_imagen(
                        imagen_nombre=filename,
                        imagen_path=f'uploads/plantas/{filename}',
                        app=current_app
                    )
                else:
                    flash('Formato de imagen no válido. Use JPG, PNG, GIF o WebP.', 'warning')
            
            # Si se usa URL externa
            elif imagen_url:
                if es_url_imagen_valida(imagen_url):
                    planta.actualizar_imagen(
                        imagen_url=imagen_url,
                        app=current_app
                    )
                else:
                    flash('La URL no parece ser una imagen válida.', 'warning')
            
            db.session.commit()
            flash(f'Planta "{planta.nombre}" actualizada correctamente', 'success')
            return redirect(url_for('plants.detalle_planta', id=planta.id))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error al actualizar planta {id}: {str(e)}")
            flash(f'Error al actualizar la planta: {str(e)}', 'error')
            return render_template('plants/editar.html', planta=planta)
    
    return render_template('plants/editar.html', planta=planta)


# ========== FUNCIONES AUXILIARES PARA IMÁGENES ==========

def allowed_image_file(filename):
    """Verificar si el archivo es una imagen permitida"""
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def guardar_imagen(file, planta_id):
    """Guardar imagen en el sistema de archivos"""
    try:
        # Crear carpeta si no existe
        upload_folder = current_app.config.get('PLANTAS_UPLOAD_FOLDER', 
                                             os.path.join(current_app.static_folder, 'uploads', 'plantas'))
        os.makedirs(upload_folder, exist_ok=True)
        
        # Generar nombre único para la imagen
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
        filename = f"planta_{planta_id}_{timestamp}.{ext}"
        filepath = os.path.join(upload_folder, filename)
        
        # Redimensionar y guardar imagen
        try:
            from PIL import Image
            img = Image.open(file)
            
            # Redimensionar manteniendo aspecto (máx 800x800)
            img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            
            # Convertir a RGB si es RGBA
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            # Guardar imagen optimizada
            img.save(filepath, 'JPEG' if ext in ['jpg', 'jpeg'] else ext.upper(), 
                     quality=85, optimize=True)
            
        except ImportError:
            # Si no hay PIL, guardar sin procesar
            file.save(filepath)
        except Exception as e:
            # Fallback: guardar sin procesar
            current_app.logger.warning(f"No se pudo procesar imagen: {e}")
            file.save(filepath)
        
        current_app.logger.info(f"Imagen guardada: {filepath}")
        return filename
        
    except Exception as e:
        current_app.logger.error(f"Error guardando imagen: {e}")
        raise

def es_url_imagen_valida(url):
    """Validar que una URL sea de imagen válida"""
    if not url:
        return False
    
    # Verificar extensiones de imagen comunes
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}
    url_lower = url.lower()
    
    for ext in image_extensions:
        if url_lower.endswith(ext):
            return True
    
    # Verificar patrones comunes de servicios de imágenes
    image_patterns = [
        'imgur.com',
        'i.imgur.com',
        'imageshack.com',
        'flickr.com',
        'photobucket.com',
        'dropbox.com',
        'drive.google.com',
        'cloudinary.com',
        's3.amazonaws.com'
    ]
    
    for pattern in image_patterns:
        if pattern in url_lower:
            return True
    
    return False

@plants_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_planta(id):
    if current_user.rol == 'cliente':
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('tienda.tienda_index'))
    
    planta = Planta.query.get_or_404(id)
    
    if current_user.rol != 'admin' and planta.usuario_id != current_user.id:
        flash('No tienes permiso para eliminar esta planta', 'danger')
        return redirect(url_for('plants.listar_plantas'))
    
    db.session.delete(planta)
    db.session.commit()
    
    flash(f'Planta "{planta.nombre}" eliminada correctamente', 'success')
    return redirect(url_for('plants.listar_plantas'))

# ========== RUTAS DE RIEGO ==========
@plants_bp.route('/<int:id>/registrar-riego', methods=['GET'])
@login_required
def mostrar_formulario_riego(id):
    if current_user.rol == 'cliente':
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('tienda.tienda_index'))
    
    planta = Planta.query.get_or_404(id)
    
    if current_user.rol != 'admin' and planta.usuario_id != current_user.id:
        flash('No tienes permiso para registrar riegos en esta planta', 'danger')
        return redirect(url_for('plants.listar_plantas'))
    
    riegos_recientes = RegistroRiego.query.filter_by(id_planta=id)\
        .order_by(RegistroRiego.fecha_riego.desc())\
        .limit(5)\
        .all()
    
    return render_template('plants/registrar_riego.html', 
                         planta=planta,
                         riegos_recientes=riegos_recientes,
                         today=datetime.now().strftime('%Y-%m-%d'),
                         now=datetime.now())

@plants_bp.route('/guardar-riego', methods=['POST'])
@login_required
def guardar_riego():
    if current_user.rol == 'cliente':
        flash('Acceso no autorizado', 'danger')
        return redirect(url_for('tienda.tienda_index'))
    
    try:
        id_planta = request.form.get('id_planta')
        fecha_str = request.form.get('fecha_riego')
        hora_str = request.form.get('hora_riego')
        cantidad_agua = request.form.get('cantidad_agua')
        tipo_riego = request.form.get('tipo_riego')
        notas = request.form.get('notas', '').strip()
        
        if not all([id_planta, fecha_str, hora_str, cantidad_agua, tipo_riego]):
            flash('Todos los campos obligatorios deben ser completados', 'error')
            return redirect(url_for('plants.mostrar_formulario_riego', id=id_planta))
        
        planta = Planta.query.get(id_planta)
        if not planta:
            flash('Planta no encontrada', 'error')
            return redirect(url_for('plants.listar_plantas'))
        
        if current_user.rol != 'admin' and planta.usuario_id != current_user.id:
            flash('No tienes permiso para registrar riegos en esta planta', 'danger')
            return redirect(url_for('plants.listar_plantas'))
        
        fecha_completa_str = f"{fecha_str} {hora_str}"
        fecha_riego = datetime.strptime(fecha_completa_str, '%Y-%m-%d %H:%M')
        
        nuevo_riego = RegistroRiego(
            id_planta=int(id_planta),
            fecha_riego=fecha_riego,
            cantidad_agua=int(cantidad_agua),
            tipo_riego=tipo_riego,
            notas=notas
        )
        
        db.session.add(nuevo_riego)
        db.session.commit()
        
        flash(f'¡Riego registrado exitosamente para {planta.nombre}!', 'success')
        return redirect(url_for('plants.detalle_planta', id=id_planta))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al registrar el riego: {str(e)}', 'error')
        return redirect(url_for('plants.mostrar_formulario_riego', id=request.form.get('id_planta', 1)))

# ========== GESTIÓN TIENDA ==========
@plants_bp.route('/<int:id>/agregar-tienda', methods=['POST'])
@login_required
def agregar_a_tienda(id):
    """Agregar una planta a la tienda online"""
    if current_user.rol == 'cliente':
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
    
    planta = Planta.query.get_or_404(id)
    
    if current_user.rol != 'admin' and planta.usuario_id != current_user.id:
        return jsonify({'success': False, 'message': 'No tienes permiso'}), 403
    
    try:
        planta.precio = float(request.form.get('precio', 0))
        planta.descripcion = request.form.get('descripcion', '')
        planta.stock = int(request.form.get('stock', 0))
        planta.categoria = request.form.get('categoria', '')
        planta.disponible_venta = True
        
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': f'Planta "{planta.nombre}" agregada a la tienda exitosamente'
            })
        
        flash(f'Planta "{planta.nombre}" agregada a la tienda exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': f'Error al agregar a la tienda: {str(e)}'
            })
        
        flash(f'Error al agregar a la tienda: {str(e)}', 'error')
    
    return redirect(url_for('plants.listar_plantas'))

@plants_bp.route('/<int:id>/actualizar-tienda', methods=['POST'])
@login_required
def actualizar_tienda(id):
    """Actualizar información de una planta en la tienda"""
    if current_user.rol == 'cliente':
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
    
    planta = Planta.query.get_or_404(id)
    
    if current_user.rol != 'admin' and planta.usuario_id != current_user.id:
        return jsonify({'success': False, 'message': 'No tienes permiso'}), 403
    
    try:
        planta.precio = float(request.form.get('precio', 0))
        planta.stock = int(request.form.get('stock', 0))
        
        disponible_venta = request.form.get('disponible_venta')
        if disponible_venta == 'true':
            planta.disponible_venta = True
        elif disponible_venta == 'false':
            planta.disponible_venta = False
        
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': f'Información de tienda actualizada para "{planta.nombre}"'
            })
        
        flash(f'Información de tienda actualizada para "{planta.nombre}"', 'success')
        
    except Exception as e:
        db.session.rollback()
        
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
    """Página principal de la tienda para clientes"""
    if current_user.rol != 'cliente':
        flash('Acceso solo para clientes', 'danger')
        return redirect(url_for('main.dashboard'))
    
    plantas_disponibles = Planta.query.filter_by(
        disponible_venta=True,
        estado='activa'
    ).filter(Planta.stock > 0).all()
    
    categorias = db.session.query(Planta.categoria).filter(
        Planta.disponible_venta == True,
        Planta.categoria.isnot(None)
    ).distinct().all()
    categorias = [cat[0] for cat in categorias if cat[0]]
    
    return render_template('tienda/index.html', 
                         plantas=plantas_disponibles,
                         categorias=categorias)

@tienda_bp.route('/planta/<int:id>')
@login_required
def ver_planta_tienda(id):
    """Ver detalles de una planta en la tienda"""
    if current_user.rol != 'cliente':
        flash('Acceso solo para clientes', 'danger')
        return redirect(url_for('main.dashboard'))
    
    planta = Planta.query.filter_by(
        id=id,
        disponible_venta=True,
        estado='activa'
    ).first_or_404()
    
    plantas_relacionadas = []
    if planta.categoria:
        plantas_relacionadas = Planta.query.filter(
            Planta.categoria == planta.categoria,
            Planta.id != planta.id,
            Planta.disponible_venta == True,
            Planta.stock > 0
        ).limit(4).all()
    
    return render_template('tienda/detalle_planta.html',
                         planta=planta,
                         plantas_relacionadas=plantas_relacionadas)

@tienda_bp.route('/categoria/<string:categoria>')
@login_required
def plantas_por_categoria(categoria):
    """Ver plantas por categoría"""
    if current_user.rol != 'cliente':
        flash('Acceso solo para clientes', 'danger')
        return redirect(url_for('main.dashboard'))
    
    plantas = Planta.query.filter(
        Planta.categoria == categoria,
        Planta.disponible_venta == True,
        Planta.estado == 'activa',
        Planta.stock > 0
    ).all()
    
    return render_template('tienda/categoria.html',
                         plantas=plantas,
                         categoria=categoria)

@tienda_bp.route('/buscar')
@login_required
def buscar_plantas():
    """Buscar plantas en la tienda"""
    if current_user.rol != 'cliente':
        flash('Acceso solo para clientes', 'danger')
        return redirect(url_for('main.dashboard'))
    
    query = request.args.get('q', '')
    precio_min = request.args.get('precio_min', type=float)
    precio_max = request.args.get('precio_max', type=float)
    categoria = request.args.get('categoria', '')
    
    plantas_query = Planta.query.filter(
        Planta.disponible_venta == True,
        Planta.estado == 'activa',
        Planta.stock > 0
    )
    
    if query:
        plantas_query = plantas_query.filter(
            db.or_(
                Planta.nombre.ilike(f'%{query}%'),
                Planta.especie.ilike(f'%{query}%'),
                Planta.descripcion.ilike(f'%{query}%')
            )
        )
    
    if precio_min is not None:
        plantas_query = plantas_query.filter(Planta.precio >= precio_min)
    
    if precio_max is not None:
        plantas_query = plantas_query.filter(Planta.precio <= precio_max)
    
    if categoria:
        plantas_query = plantas_query.filter(Planta.categoria == categoria)
    
    plantas = plantas_query.all()
    
    categorias = db.session.query(Planta.categoria).filter(
        Planta.disponible_venta == True,
        Planta.categoria.isnot(None)
    ).distinct().all()
    categorias = [cat[0] for cat in categorias if cat[0]]
    
    return render_template('tienda/buscar.html',
                         plantas=plantas,
                         query=query,
                         categorias=categorias,
                         precio_min=precio_min,
                         precio_max=precio_max,
                         categoria_seleccionada=categoria)

@tienda_bp.route('/api/plantas-disponibles')
@login_required
def api_plantas_disponibles():
    """API para obtener plantas disponibles (JSON)"""
    if current_user.rol != 'cliente':
        return jsonify({'error': 'No autorizado'}), 403
    
    plantas = Planta.query.filter_by(
        disponible_venta=True,
        estado='activa'
    ).filter(Planta.stock > 0).all()
    
    resultado = []
    for planta in plantas:
        resultado.append({
            'id': planta.id,
            'nombre': planta.nombre,
            'especie': planta.especie,
            'precio': planta.precio,
            'descripcion': planta.descripcion,
            'stock': planta.stock,
            'categoria': planta.categoria,
            'imagen_url': planta.imagen_url
        })
    
    return jsonify(resultado)

# ========== CARRITO DE COMPRAS ==========
@tienda_bp.route('/carrito')
@login_required
def ver_carrito():
    """Ver carrito de compras"""
    if current_user.rol != 'cliente':
        flash('Acceso solo para clientes', 'danger')
        return redirect(url_for('main.dashboard'))
    
    carrito = obtener_carrito()
    plantas_carrito = []
    subtotal = 0.0
    
    for planta_id, item in carrito.items():
        planta = Planta.query.get(int(planta_id))
        if planta and planta.disponible_venta and planta.stock > 0:
            if float(item['precio']) != float(planta.precio):
                item['precio'] = str(planta.precio)
            
            cantidad = item['cantidad']
            precio_unitario = float(item['precio'])
            total_item = cantidad * precio_unitario
            
            plantas_carrito.append({
                'id': planta.id,
                'nombre': planta.nombre,
                'cantidad': cantidad,
                'precio_unitario': precio_unitario,
                'total_item': total_item,
                'stock': planta.stock,
                'imagen_url': planta.imagen_url,
                'categoria': planta.categoria
            })
            
            subtotal += total_item
    
    envio = 5.99 if subtotal < 50 else 0
    iva = subtotal * 0.12
    total = subtotal + envio + iva
    
    if len(plantas_carrito) != len(carrito):
        nuevo_carrito = {}
        for item in plantas_carrito:
            nuevo_carrito[str(item['id'])] = {
                'cantidad': item['cantidad'],
                'precio': str(item['precio_unitario'])
            }
        guardar_carrito(nuevo_carrito)
    
    return render_template('tienda/carrito.html',
                         plantas_carrito=plantas_carrito,
                         subtotal=subtotal,
                         envio=envio,
                         iva=iva,
                         total=total,
                         carrito_vacio=len(plantas_carrito) == 0)

@tienda_bp.route('/carrito/agregar/<int:planta_id>', methods=['POST'])
@login_required
def agregar_al_carrito(planta_id):
    """Agregar una planta al carrito"""
    if current_user.rol != 'cliente':
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
    
    planta = Planta.query.filter_by(
        id=planta_id,
        disponible_venta=True,
        estado='activa'
    ).first()
    
    if not planta:
        return jsonify({'success': False, 'message': 'Planta no disponible'}), 404
    
    if planta.stock <= 0:
        return jsonify({'success': False, 'message': 'Planta agotada'}), 400
    
    cantidad = request.json.get('cantidad', 1)
    
    carrito = obtener_carrito()
    planta_key = str(planta_id)
    
    if planta_key in carrito:
        nueva_cantidad = carrito[planta_key]['cantidad'] + cantidad
        if nueva_cantidad > planta.stock:
            return jsonify({
                'success': False, 
                'message': f'Solo quedan {planta.stock} unidades disponibles'
            }), 400
        carrito[planta_key]['cantidad'] = nueva_cantidad
    else:
        carrito[planta_key] = {
            'cantidad': cantidad,
            'precio': str(planta.precio)
        }
    
    guardar_carrito(carrito)
    
    return jsonify({
        'success': True,
        'message': f'{planta.nombre} agregada al carrito',
        'carrito_count': sum(item['cantidad'] for item in carrito.values())
    })

@tienda_bp.route('/carrito/actualizar/<int:planta_id>', methods=['POST'])
@login_required
def actualizar_carrito(planta_id):
    """Actualizar cantidad de una planta en el carrito"""
    if current_user.rol != 'cliente':
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
    
    planta = Planta.query.get(planta_id)
    if not planta or not planta.disponible_venta:
        return jsonify({'success': False, 'message': 'Planta no disponible'}), 404
    
    nueva_cantidad = request.json.get('cantidad', 1)
    
    if nueva_cantidad <= 0:
        return jsonify({'success': False, 'message': 'Cantidad inválida'}), 400
    
    if nueva_cantidad > planta.stock:
        return jsonify({
            'success': False, 
            'message': f'Solo hay {planta.stock} unidades disponibles'
        }), 400
    
    carrito = obtener_carrito()
    planta_key = str(planta_id)
    
    if planta_key in carrito:
        carrito[planta_key]['cantidad'] = nueva_cantidad
        guardar_carrito(carrito)
        
        return jsonify({
            'success': True,
            'message': 'Cantidad actualizada',
            'carrito_count': sum(item['cantidad'] for item in carrito.values())
        })
    
    return jsonify({'success': False, 'message': 'Planta no encontrada en el carrito'}), 404

@tienda_bp.route('/carrito/eliminar/<int:planta_id>', methods=['POST'])
@login_required
def eliminar_del_carrito(planta_id):
    """Eliminar una planta del carrito"""
    if current_user.rol != 'cliente':
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
    
    carrito = obtener_carrito()
    planta_key = str(planta_id)
    
    if planta_key in carrito:
        del carrito[planta_key]
        guardar_carrito(carrito)
        
        return jsonify({
            'success': True,
            'message': 'Planta eliminada del carrito',
            'carrito_count': sum(item['cantidad'] for item in carrito.values())
        })
    
    return jsonify({'success': False, 'message': 'Planta no encontrada en el carrito'}), 404

@tienda_bp.route('/carrito/vaciar', methods=['POST'])
@login_required
def vaciar_carrito():
    """Vaciar todo el carrito"""
    if current_user.rol != 'cliente':
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
    
    guardar_carrito({})
    
    return jsonify({
        'success': True,
        'message': 'Carrito vaciado',
        'carrito_count': 0
    })

@tienda_bp.route('/carrito/cantidad')
@login_required
def cantidad_carrito():
    """Obtener cantidad total de items en el carrito"""
    if current_user.rol != 'cliente':
        return jsonify({'error': 'No autorizado'}), 403
    
    carrito = obtener_carrito()
    total_items = sum(item['cantidad'] for item in carrito.values())
    
    return jsonify({
        'success': True,
        'total_items': total_items
    })

# ========== PEDIDOS ==========
@tienda_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Proceso de checkout/pago"""
    if current_user.rol != 'cliente':
        flash('Acceso solo para clientes', 'danger')
        return redirect(url_for('main.dashboard'))
    
    carrito = obtener_carrito()
    if not carrito:
        flash('Tu carrito está vacío', 'warning')
        return redirect(url_for('tienda.ver_carrito'))
    
    items_sin_stock = []
    plantas_carrito = []
    subtotal = 0.0
    
    for planta_id, item in carrito.items():
        planta = Planta.query.get(int(planta_id))
        if planta:
            if planta.stock < item['cantidad']:
                items_sin_stock.append({
                    'nombre': planta.nombre,
                    'solicitado': item['cantidad'],
                    'disponible': planta.stock
                })
            
            precio_unitario = float(item['precio'])
            cantidad = item['cantidad']
            total_item = precio_unitario * cantidad
            
            plantas_carrito.append({
                'id': planta.id,
                'nombre': planta.nombre,
                'precio_unitario': precio_unitario,
                'cantidad': cantidad,
                'total_item': total_item,
                'imagen_url': planta.imagen_url,
                'categoria': planta.categoria,
                'stock': planta.stock
            })
            
            subtotal += total_item
    
    if items_sin_stock:
        mensaje = "Algunos productos no tienen suficiente stock:<br>"
        for item in items_sin_stock:
            mensaje += f"- {item['nombre']}: Solicitado {item['solicitado']}, Disponible {item['disponible']}<br>"
        flash(mensaje, 'danger')
        return redirect(url_for('tienda.ver_carrito'))
    
    envio = 5.99 if subtotal < 50 else 0
    iva = subtotal * 0.12
    total = subtotal + envio + iva
    
    if request.method == 'POST':
        try:
            direccion_envio = request.form.get('direccion_envio', '').strip()
            telefono_contacto = request.form.get('telefono_contacto', '').strip()
            notas_pedido = request.form.get('notas_pedido', '').strip()
            metodo_pago = request.form.get('metodo_pago', 'transferencia')
            referencia = request.form.get('referencia', '')
            nombre_cliente = request.form.get('nombre', current_user.nombre)
            
            if not direccion_envio:
                flash('La dirección de envío es requerida', 'danger')
                return render_template('tienda/checkout.html',
                                     plantas_carrito=plantas_carrito,
                                     subtotal=subtotal,
                                     envio=envio,
                                     iva=iva,
                                     total=total)
            
            if not telefono_contacto:
                flash('El teléfono de contacto es requerido', 'danger')
                return render_template('tienda/checkout.html',
                                     plantas_carrito=plantas_carrito,
                                     subtotal=subtotal,
                                     envio=envio,
                                     iva=iva,
                                     total=total)
            
            if not nombre_cliente:
                flash('El nombre es requerido', 'danger')
                return render_template('tienda/checkout.html',
                                     plantas_carrito=plantas_carrito,
                                     subtotal=subtotal,
                                     envio=envio,
                                     iva=iva,
                                     total=total)
            
            for planta_id, item in carrito.items():
                planta = Planta.query.get(int(planta_id))
                if planta and planta.stock < item['cantidad']:
                    flash(f'Lo sentimos, {planta.nombre} ya no tiene suficiente stock. Solo quedan {planta.stock} unidades.', 'danger')
                    return redirect(url_for('tienda.ver_carrito'))
            
            nuevo_pedido = Pedido(
                id_cliente=current_user.id,
                costo_total=total,
                estado_pedido='pendiente',
                fecha_orden=datetime.utcnow()
            )
            
            db.session.add(nuevo_pedido)
            db.session.flush()
            
            current_app.logger.info(f"Pedido creado con ID: {nuevo_pedido.id_pedido}")
            
            for planta_id, item in carrito.items():
                planta = Planta.query.get(int(planta_id))
                if planta:
                    detalle = PedidoDetalle(
                        id_pedido=nuevo_pedido.id_pedido,
                        id_planta=planta.id,
                        cantidad=item['cantidad'],
                        precio_en_compra=float(item['precio'])
                    )
                    
                    db.session.add(detalle)
                    
                    planta.stock -= item['cantidad']
                    if planta.stock <= 0:
                        planta.disponible_venta = False
                        planta.stock = 0
            
            db.session.commit()
            
            guardar_carrito({})
            
            mensaje_exito = f'¡Pedido #{nuevo_pedido.id_pedido} realizado exitosamente!<br>'
            mensaje_exito += f'Total: ${total:.2f}<br>'
            mensaje_exito += f'Método de pago: {metodo_pago}<br>'
            if referencia:
                mensaje_exito += f'Referencia: {referencia}<br>'
            mensaje_exito += 'Nos pondremos en contacto contigo pronto.'
            
            flash(mensaje_exito, 'success')
            return redirect(url_for('tienda.mis_pedidos'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error completo al procesar pedido: {str(e)}")
            current_app.logger.error(f"Traceback: {traceback.format_exc()}")
            flash(f'Error al procesar el pedido: {str(e)}', 'danger')
            return render_template('tienda/checkout.html',
                                 plantas_carrito=plantas_carrito,
                                 subtotal=subtotal,
                                 envio=envio,
                                 iva=iva,
                                 total=total)
    
    return render_template('tienda/checkout.html',
                         plantas_carrito=plantas_carrito,
                         subtotal=subtotal,
                         envio=envio,
                         iva=iva,
                         total=total)

@tienda_bp.route('/mis-pedidos')
@login_required
def mis_pedidos():
    """Ver historial de pedidos del cliente"""
    if current_user.rol != 'cliente':
        flash('Acceso solo para clientes', 'danger')
        return redirect(url_for('main.dashboard'))
    
    pedidos = Pedido.query.filter_by(id_cliente=current_user.id)\
        .order_by(Pedido.fecha_orden.desc())\
        .all()
    
    return render_template('tienda/mis_pedidos.html', pedidos=pedidos)

@tienda_bp.route('/pedido/<int:id>')
@login_required
def ver_pedido(id):
    """Ver detalles de un pedido específico"""
    pedido = Pedido.query.get_or_404(id)
    
    if current_user.rol != 'cliente' or pedido.id_cliente != current_user.id:
        flash('No tienes permiso para ver este pedido', 'danger')
        return redirect(url_for('tienda.mis_pedidos'))
    
    detalles = PedidoDetalle.query.filter_by(id_pedido=id).all()
    
    plantas_info = []
    total_pedido = 0
    
    for detalle in detalles:
        planta = Planta.query.get(detalle.id_planta)
        if planta:
            subtotal = detalle.cantidad * detalle.precio_en_compra
            total_pedido += subtotal
            
            plantas_info.append({
                'id': planta.id,
                'nombre': planta.nombre,
                'cantidad': detalle.cantidad,
                'precio_unitario': detalle.precio_en_compra,
                'subtotal': subtotal,
                'imagen_url': planta.imagen_url,
                'categoria': planta.categoria
            })
    
    return render_template('tienda/detalle_pedido.html',
                         pedido=pedido,
                         detalles=detalles,
                         plantas_info=plantas_info,
                         total_pedido=total_pedido)

@tienda_bp.route('/pedido/<int:id>/cancelar', methods=['POST'])
@login_required
def cancelar_pedido(id):
    """Cancelar un pedido"""
    pedido = Pedido.query.get_or_404(id)
    
    if current_user.rol != 'cliente' or pedido.id_cliente != current_user.id:
        flash('No tienes permiso para cancelar este pedido', 'danger')
        return redirect(url_for('tienda.mis_pedidos'))
    
    if pedido.estado_pedido not in ['pendiente', 'procesando']:
        flash('Este pedido no se puede cancelar en su estado actual', 'warning')
        return redirect(url_for('tienda.ver_pedido', id=id))
    
    try:
        detalles = PedidoDetalle.query.filter_by(id_pedido=id).all()
        for detalle in detalles:
            planta = Planta.query.get(detalle.id_planta)
            if planta:
                planta.stock += detalle.cantidad
                planta.disponible_venta = True
        
        pedido.estado_pedido = 'cancelado'
        
        db.session.commit()
        flash('Pedido cancelado exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cancelar el pedido: {str(e)}', 'danger')
    
    return redirect(url_for('tienda.ver_pedido', id=id))

# ========== PERFIL CLIENTE ==========
@tienda_bp.route('/mi-perfil', methods=['GET', 'POST'])
@login_required
def mi_perfil():
    """Gestión del perfil del cliente"""
    if current_user.rol != 'cliente':
        flash('Acceso solo para clientes', 'danger')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        try:
            current_user.nombre = request.form.get('nombre', '').strip()
            current_user.telefono = request.form.get('telefono', '').strip()
            current_user.direccion = request.form.get('direccion', '').strip()
            
            nueva_contrasenia = request.form.get('nueva_contrasenia', '')
            confirmar_contrasenia = request.form.get('confirmar_contrasenia', '')
            
            if nueva_contrasenia:
                if len(nueva_contrasenia) < 6:
                    flash('La contraseña debe tener al menos 6 caracteres', 'danger')
                elif nueva_contrasenia != confirmar_contrasenia:
                    flash('Las contraseñas no coinciden', 'danger')
                else:
                    from werkzeug.security import generate_password_hash
                    current_user.contrasenia_hash = generate_password_hash(nueva_contrasenia)
                    flash('Contraseña actualizada exitosamente', 'success')
            
            db.session.commit()
            flash('Perfil actualizado exitosamente', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar perfil: {str(e)}', 'danger')
    
    return render_template('tienda/mi_perfil.html')

# ========== ADMIN - GESTIÓN DE PEDIDOS ==========
@main_bp.route('/admin/pedidos')
@login_required
def admin_pedidos():
    """Gestión de pedidos para administradores"""
    if current_user.rol != 'admin':
        flash('Acceso solo para administradores', 'danger')
        return redirect(url_for('main.dashboard'))
    
    estado = request.args.get('estado', 'todos')
    
    if estado == 'todos':
        pedidos = Pedido.query.order_by(Pedido.fecha_orden.desc()).all()
    else:
        pedidos = Pedido.query.filter_by(estado_pedido=estado)\
            .order_by(Pedido.fecha_orden.desc())\
            .all()
    
    return render_template('admin/pedidos.html', pedidos=pedidos, estado=estado)

@main_bp.route('/admin/pedido/<int:id>')
@login_required
def admin_ver_pedido(id):
    """Ver detalles de un pedido como administrador"""
    if current_user.rol != 'admin':
        flash('Acceso solo para administradores', 'danger')
        return redirect(url_for('main.dashboard'))
    
    pedido = Pedido.query.get_or_404(id)
    detalles = PedidoDetalle.query.filter_by(id_pedido=id).all()
    
    return render_template('admin/detalle_pedido.html',
                         pedido=pedido,
                         detalles=detalles)

@main_bp.route('/admin/pedido/<int:id>/actualizar-estado', methods=['POST'])
@login_required
def actualizar_estado_pedido(id):
    """Actualizar estado de un pedido (admin)"""
    if current_user.rol != 'admin':
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
    
    pedido = Pedido.query.get_or_404(id)
    nuevo_estado = request.json.get('estado', '')
    
    if nuevo_estado not in ['pendiente', 'procesando', 'enviado', 'completado', 'cancelado']:
        return jsonify({'success': False, 'message': 'Estado inválido'}), 400
    
    try:
        pedido.estado_pedido = nuevo_estado
        
        if nuevo_estado == 'enviado':
            pedido.fecha_envio = datetime.utcnow()
        elif nuevo_estado == 'completado':
            pedido.fecha_completado = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Estado actualizado a {nuevo_estado}',
            'estado': nuevo_estado
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

# ========== ADMIN - ESTADÍSTICAS TIENDA ==========
@main_bp.route('/admin/estadisticas-tienda')
@login_required
def estadisticas_tienda():
    """Estadísticas de la tienda para administradores"""
    if current_user.rol != 'admin':
        flash('Acceso solo para administradores', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # ========== DATOS REALES DE LA BASE DE DATOS ==========
    
    # Ventas totales
    ventas_totales_result = db.session.query(db.func.sum(Pedido.costo_total)).scalar()
    ventas_totales = float(ventas_totales_result) if ventas_totales_result else 0.0
    
    # Total de pedidos
    total_pedidos = Pedido.query.count()
    
    # Pedidos por estado
    pedidos_pendientes = Pedido.query.filter_by(estado_pedido='pendiente').count()
    pedidos_procesando = Pedido.query.filter_by(estado_pedido='procesando').count()
    pedidos_completados = Pedido.query.filter_by(estado_pedido='completado').count()
    pedidos_cancelados = Pedido.query.filter_by(estado_pedido='cancelado').count()
    
    # Productos más vendidos
    productos_vendidos = db.session.query(
        Planta.nombre,
        db.func.sum(PedidoDetalle.cantidad).label('total_vendido'),
        db.func.sum(PedidoDetalle.precio_en_compra * PedidoDetalle.cantidad).label('ingresos')
    ).join(PedidoDetalle, Planta.id == PedidoDetalle.id_planta)\
     .join(Pedido, PedidoDetalle.id_pedido == Pedido.id_pedido)\
     .filter(Pedido.estado_pedido != 'cancelado')\
     .group_by(Planta.id, Planta.nombre)\
     .order_by(db.desc('total_vendido'))\
     .limit(10)\
     .all()
    
    # Convertir a lista de diccionarios para mejor manejo en el template
    productos_vendidos_list = []
    for producto in productos_vendidos:
        productos_vendidos_list.append({
            'nombre': producto.nombre,
            'total_vendido': producto.total_vendido or 0,
            'ingresos': float(producto.ingresos) if producto.ingresos else 0.0
        })
    
    # Ventas mensuales (últimos 6 meses)
    seis_meses_atras = datetime.utcnow() - timedelta(days=180)
    ventas_mensuales_raw = db.session.query(
        db.func.strftime('%Y-%m', Pedido.fecha_orden).label('mes'),
        db.func.count(Pedido.id_pedido).label('total_pedidos'),
        db.func.sum(Pedido.costo_total).label('ventas_totales')
    ).filter(Pedido.fecha_orden >= seis_meses_atras)\
     .filter(Pedido.estado_pedido != 'cancelado')\
     .group_by('mes')\
     .order_by('mes')\
     .all()
    
    # Convertir a lista de diccionarios y formatear mes
    ventas_mensuales = []
    for venta in ventas_mensuales_raw:
        # Formatear mes a nombre (ej: "2024-01" -> "Enero 2024")
        try:
            anio, mes_num = venta.mes.split('-')
            meses_espanol = {
                '01': 'Enero', '02': 'Febrero', '03': 'Marzo', '04': 'Abril',
                '05': 'Mayo', '06': 'Junio', '07': 'Julio', '08': 'Agosto',
                '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'
            }
            mes_nombre = f"{meses_espanol.get(mes_num, mes_num)} {anio}"
        except:
            mes_nombre = venta.mes
        
        ventas_mensuales.append({
            'mes': mes_nombre,
            'total_pedidos': venta.total_pedidos or 0,
            'ventas_totales': float(venta.ventas_totales) if venta.ventas_totales else 0.0
        })
    
    # Total clientes
    total_clientes = Usuario.query.filter_by(rol='cliente').count()
    
    # Clientes activos (que han realizado al menos un pedido)
    clientes_activos = db.session.query(Pedido.id_cliente).distinct().count()
    
    # Ticket promedio (si hay pedidos)
    ticket_promedio = ventas_totales / total_pedidos if total_pedidos > 0 else 0
    
    # Tasa de conversión (clientes que han comprado vs total clientes)
    tasa_conversion = (clientes_activos / total_clientes * 100) if total_clientes > 0 else 0
    
    # Tasa de cancelación
    tasa_cancelacion = (pedidos_cancelados / total_pedidos * 100) if total_pedidos > 0 else 0
    
    # ========== DATOS PARA EL TEMPLATE ==========
    
    return render_template('admin/estadisticas_tienda.html',
                         ventas_totales=ventas_totales,
                         total_pedidos=total_pedidos,
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

# ========== REPORTES ROUTES ==========
@reports_bp.route('/')
@login_required
def reportes():
    if current_user.rol != 'admin':
        flash('Solo administradores pueden ver reportes', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Obtener estadísticas de plantas
    total_plantas = Planta.query.count()
    plantas_activas = Planta.query.filter_by(estado='activa').count()
    plantas_en_venta = Planta.query.filter_by(disponible_venta=True, estado='activa').count()
    
    plantas_stats = {
        'total': total_plantas,
        'activas': plantas_activas,
        'en_venta': plantas_en_venta,
        'tendencia': 5.2  # Porcentaje de crecimiento (podrías calcularlo)
    }
    
    # Obtener estadísticas de pedidos
    total_pedidos = Pedido.query.count()
    pedidos_completados = Pedido.query.filter_by(estado_pedido='completado').count()
    ventas_totales = db.session.query(db.func.sum(Pedido.costo_total)).scalar() or 0
    
    # Pedidos por estado
    estados_pedidos = {}
    for estado in ['pendiente', 'procesando', 'enviado', 'completado', 'cancelado']:
        estados_pedidos[estado] = Pedido.query.filter_by(estado_pedido=estado).count()
    
    # Calcular ticket promedio
    ticket_promedio = ventas_totales / pedidos_completados if pedidos_completados > 0 else 0
    
    # Calcular productos por pedido
    total_productos = db.session.query(db.func.sum(PedidoDetalle.cantidad)).scalar() or 0
    productos_por_pedido = total_productos / pedidos_completados if pedidos_completados > 0 else 0
    
    pedidos_stats = {
        'total': total_pedidos,
        'completados': pedidos_completados,
        'ventas_totales': float(ventas_totales),
        'por_estado': estados_pedidos,
        'ticket_promedio': float(ticket_promedio),
        'productos_por_pedido': float(productos_por_pedido),
        'tendencia_ventas': 12.5,  # Porcentaje de crecimiento
        'ventas_hoy': calcular_ventas_hoy()
    }
    
    # Obtener estadísticas de clientes
    total_clientes = Usuario.query.filter_by(rol='cliente').count()
    clientes_activos = Usuario.query.filter_by(rol='cliente', estado='activo').count()
    
    # Clientes con pedidos
    clientes_con_pedidos = db.session.query(Usuario).join(Pedido).filter(
        Usuario.rol == 'cliente'
    ).distinct().count()
    
    # Nuevos clientes este mes
    primer_dia_mes = datetime(datetime.now().year, datetime.now().month, 1)
    nuevos_este_mes = Usuario.query.filter(
        Usuario.rol == 'cliente',
        Usuario.fecha_registro >= primer_dia_mes
    ).count()
    
    clientes_stats = {
        'total': total_clientes,
        'activos': clientes_activos,
        'con_pedidos': clientes_con_pedidos,
        'nuevos_este_mes': nuevos_este_mes
    }
    
    # Obtener estadísticas de respaldos
    total_respaldos = Respaldo.query.count()
    respaldos_completos = Respaldo.query.filter(Respaldo.tipo_respaldo.like('%completo%')).count()
    respaldos_en_usb = Respaldo.query.filter_by(almacenamiento='usb').count()
    
    # Calcular tamaño total
    tamaño_total_mb = db.session.query(db.func.sum(Respaldo.tamaño_mb)).scalar() or 0
    tamaño_total_gb = tamaño_total_mb / 1024
    
    # Calcular tamaño por almacenamiento
    tamaño_local_mb = db.session.query(db.func.sum(Respaldo.tamaño_mb)).filter(
        Respaldo.almacenamiento == 'local'
    ).scalar() or 0
    
    tamaño_usb_mb = db.session.query(db.func.sum(Respaldo.tamaño_mb)).filter(
        Respaldo.almacenamiento == 'usb'
    ).scalar() or 0
    
    respaldos_stats = {
        'total': total_respaldos,
        'completos': respaldos_completos,
        'en_usb': respaldos_en_usb,
        'tamaño_total_mb': float(tamaño_total_mb),
        'tamaño_total_gb': float(tamaño_total_gb),
        'tamaño_local_mb': float(tamaño_local_mb),
        'tamaño_usb_mb': float(tamaño_usb_mb)
    }
    
    # Obtener accesos recientes
    accesos_recientes = HistorialAcceso.query.order_by(
        HistorialAcceso.fecha_acceso.desc()
    ).limit(5).all()
    
    # Obtener ventas mensuales para el gráfico
    ventas_mensuales = {}
    seis_meses_atras = datetime.now() - timedelta(days=180)
    
    pedidos_recientes = Pedido.query.filter(
        Pedido.fecha_orden >= seis_meses_atras
    ).all()
    
    for pedido in pedidos_recientes:
        mes = pedido.fecha_orden.strftime('%Y-%m')
        ventas_mensuales[mes] = ventas_mensuales.get(mes, 0) + float(pedido.costo_total)
    
    # Obtener top productos
    top_productos_raw = db.session.query(
        Planta.nombre,
        db.func.sum(PedidoDetalle.cantidad).label('cantidad_vendida'),
        db.func.sum(PedidoDetalle.precio_en_compra * PedidoDetalle.cantidad).label('ingresos')
    ).join(PedidoDetalle, Planta.id == PedidoDetalle.id_planta)\
     .group_by(Planta.id)\
     .order_by(db.desc('cantidad_vendida'))\
     .limit(10)\
     .all()
    
    top_productos = []
    for nombre, cantidad, ingresos in top_productos_raw:
        top_productos.append({
            'nombre': nombre,
            'cantidad_vendida': cantidad,
            'ingresos': float(ingresos) if ingresos else 0
        })
    
    # Obtener crecimiento de clientes
    crecimiento_clientes = {}
    for i in range(5, -1, -1):
        fecha = datetime.now() - timedelta(days=i*30)
        mes = fecha.strftime('%Y-%m')
        inicio_mes = fecha.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        if i == 0:
            fin_mes = datetime.now()
        else:
            siguiente_mes = fecha.replace(day=28) + timedelta(days=4)
            fin_mes = siguiente_mes.replace(day=1) - timedelta(days=1)
        
        nuevos_clientes = Usuario.query.filter(
            Usuario.rol == 'cliente',
            Usuario.fecha_registro >= inicio_mes,
            Usuario.fecha_registro <= fin_mes
        ).count()
        
        crecimiento_clientes[fecha.strftime('%b')] = nuevos_clientes
    
    # Obtener tipos de respaldos
    tipos_respaldos = {}
    tipos = db.session.query(Respaldo.tipo_respaldo, db.func.count(Respaldo.id)).group_by(Respaldo.tipo_respaldo).all()
    
    for tipo, cantidad in tipos:
        if 'completo' in tipo:
            tipos_respaldos['Completos'] = tipos_respaldos.get('Completos', 0) + cantidad
        elif 'diferencial' in tipo:
            tipos_respaldos['Diferenciales'] = tipos_respaldos.get('Diferenciales', 0) + cantidad
        elif 'copia_usb' in tipo:
            tipos_respaldos['Copias USB'] = tipos_respaldos.get('Copias USB', 0) + cantidad
        elif 'importado' in tipo:
            tipos_respaldos['Importados'] = tipos_respaldos.get('Importados', 0) + cantidad
        elif 'programado' in tipo:
            tipos_respaldos['Programados'] = tipos_respaldos.get('Programados', 0) + cantidad
        else:
            tipos_respaldos[tipo] = tipos_respaldos.get(tipo, 0) + cantidad
    
    # Obtener ventas diarias (últimos 7 días)
    ventas_diarias = {}
    for i in range(6, -1, -1):
        fecha = (datetime.now() - timedelta(days=i)).date()
        inicio_dia = datetime.combine(fecha, datetime.min.time())
        fin_dia = datetime.combine(fecha, datetime.max.time())
        
        ventas_dia = db.session.query(db.func.sum(Pedido.costo_total)).filter(
            Pedido.fecha_orden >= inicio_dia,
            Pedido.fecha_orden <= fin_dia
        ).scalar() or 0
        
        ventas_diarias[fecha.strftime('%d/%m')] = float(ventas_dia)
    
    # Obtener clientes destacados
    clientes_destacados = []
    clientes_con_compras = db.session.query(
        Usuario,
        db.func.sum(Pedido.costo_total).label('total_compras'),
        db.func.count(Pedido.id_pedido).label('total_pedidos'),
        db.func.max(Pedido.fecha_orden).label('ultimo_pedido')
    ).outerjoin(Pedido, Usuario.id == Pedido.id_cliente)\
     .filter(Usuario.rol == 'cliente')\
     .group_by(Usuario.id)\
     .order_by(db.desc('total_compras'))\
     .all()
    
    for usuario, total_compras, total_pedidos, ultimo_pedido in clientes_con_compras:
        clientes_destacados.append({
            'id': usuario.id,
            'nombre': usuario.nombre,
            'correo': usuario.correo,
            'total_compras': float(total_compras) if total_compras else 0,
            'total_pedidos': total_pedidos or 0,
            'ultimo_pedido': ultimo_pedido,
            'estado': usuario.estado
        })
    
    return render_template('reports/index.html',
                         plantas_stats=plantas_stats,
                         pedidos_stats=pedidos_stats,
                         clientes_stats=clientes_stats,
                         respaldos_stats=respaldos_stats,
                         accesos_recientes=accesos_recientes,
                         ventas_mensuales=ventas_mensuales,
                         top_productos=top_productos,
                         crecimiento_clientes=crecimiento_clientes,
                         tipos_respaldos=tipos_respaldos,
                         ventas_diarias=ventas_diarias,
                         clientes_destacados=clientes_destacados)

def calcular_ventas_hoy():
    """Calcular ventas del día actual"""
    hoy = datetime.now().date()
    inicio_hoy = datetime.combine(hoy, datetime.min.time())
    fin_hoy = datetime.combine(hoy, datetime.max.time())
    
    ventas_hoy = db.session.query(db.func.sum(Pedido.costo_total)).filter(
        Pedido.fecha_orden >= inicio_hoy,
        Pedido.fecha_orden <= fin_hoy
    ).scalar() or 0
    
    return float(ventas_hoy)

@reports_bp.route('/respaldos')
@login_required
def reporte_respaldos():
    if current_user.rol != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    respaldos = Respaldo.query.all()
    data = {
        'total': len(respaldos),
        'por_tipo': {},
        'ultimos_meses': []
    }
    
    for respaldo in respaldos:
        tipo = respaldo.tipo_respaldo
        data['por_tipo'][tipo] = data['por_tipo'].get(tipo, 0) + 1
    
    return jsonify(data)

@reports_bp.route('/accesos')
@login_required
def reporte_accesos():
    if current_user.rol != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    accesos = HistorialAcceso.query.order_by(HistorialAcceso.fecha_acceso.desc()).limit(100).all()
    
    data = {
        'total': len(accesos),
        'por_estado': {},
        'ultimos_accesos': []
    }
    
    for acceso in accesos:
        estado = acceso.estado_sesion
        data['por_estado'][estado] = data['por_estado'].get(estado, 0) + 1
        
        data['ultimos_accesos'].append({
            'usuario_id': acceso.usuario_id,
            'fecha': acceso.fecha_acceso.strftime('%Y-%m-%d %H:%M:%S'),
            'ip': acceso.ip_address,
            'estado': acceso.estado_sesion
        })
    
    return jsonify(data)

@reports_bp.route('/tienda')
@login_required
def reporte_tienda():
    if current_user.rol != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    pedidos = Pedido.query.all()
    
    ventas_por_mes = {}
    
    for pedido in pedidos:
        mes = pedido.fecha_orden.strftime('%Y-%m')
        ventas_por_mes[mes] = ventas_por_mes.get(mes, 0) + float(pedido.costo_total)
    
    return jsonify({
        'ventas_totales': sum(float(p.costo_total) for p in pedidos),
        'total_pedidos': len(pedidos),
        'ventas_por_mes': ventas_por_mes
    })

@reports_bp.route('/clientes')
@login_required
def reporte_clientes():
    if current_user.rol != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    clientes = Usuario.query.filter_by(rol='cliente').all()
    
    clientes_data = []
    for cliente in clientes:
        total_compras = db.session.query(db.func.sum(Pedido.costo_total))\
            .filter(Pedido.id_cliente == cliente.id)\
            .scalar() or 0
        
        total_pedidos = Pedido.query.filter_by(id_cliente=cliente.id).count()
        
        clientes_data.append({
            'id': cliente.id,
            'nombre': cliente.nombre,
            'correo': cliente.correo,
            'fecha_registro': cliente.fecha_registro.strftime('%Y-%m-%d') if cliente.fecha_registro else '',
            'total_compras': float(total_compras),
            'total_pedidos': total_pedidos
        })
    
    return jsonify({
        'total_clientes': len(clientes),
        'clientes': clientes_data
    })

# ========== RUTAS DE PRUEBA/DEBUG ==========
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
        'session_id': session.sid,
        'session_data': session_data,
        'carrito': obtener_carrito()
    })

@main_bp.route('/debug/set-cliente')
def debug_set_cliente():
    """Página de debug para cambiar a rol cliente (solo desarrollo)"""
    if current_app.debug and current_user.is_authenticated:
        current_user.rol = 'cliente'
        db.session.commit()
        flash('Rol cambiado a cliente', 'success')
        return redirect(url_for('tienda.tienda_index'))
    else:
        flash('No disponible en producción', 'danger')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/debug/set-admin')
def debug_set_admin():
    """Página de debug para cambiar a rol admin (solo desarrollo)"""
    if current_app.debug and current_user.is_authenticated:
        current_user.rol = 'admin'
        db.session.commit()
        flash('Rol cambiado a administrador', 'success')
        return redirect(url_for('main.dashboard'))
    else:
        flash('No disponible en producción', 'danger')
        return redirect(url_for('main.dashboard'))
    
    
    # Añade estas rutas al blueprint 'backup_bp'

@backup_bp.route('/programaciones')
@login_required
def listar_programaciones():
    """Listar todas las programaciones de respaldo"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden ver programaciones', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    programaciones = ProgramacionRespaldo.query.order_by(
        ProgramacionRespaldo.activo.desc(),
        ProgramacionRespaldo.proxima_ejecucion.asc()
    ).all()
    
    # Calcular próxima ejecución si no está calculada
    for prog in programaciones:
        if not prog.proxima_ejecucion and prog.activo:
            prog.proxima_ejecucion = prog.calcular_proxima_ejecucion()
            try:
                db.session.commit()
            except:
                db.session.rollback()
    
    return render_template('backups/programaciones.html', 
                         programaciones=programaciones,
                         usb_mounted=detectar_usb_json().get('conectado', False))

@backup_bp.route('/programaciones/crear', methods=['GET', 'POST'])
@login_required
def crear_programacion():
    """Crear nueva programación de respaldo"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden crear programaciones', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    if request.method == 'POST':
        try:
            tipo_respaldo = request.form.get('tipo_respaldo', 'completo')
            frecuencia = request.form.get('frecuencia', 'diario')
            hora = request.form.get('hora', '02:00')
            almacenamiento = request.form.get('almacenamiento', 'local')
            
            # Convertir hora a objeto time
            hora_obj = datetime.strptime(hora, '%H:%M').time()
            
            # Crear nueva programación
            nueva_programacion = ProgramacionRespaldo(
                tipo_respaldo=tipo_respaldo,
                frecuencia=frecuencia,
                hora_ejecucion=hora_obj,
                almacenamiento=almacenamiento,
                usuario_creador=current_user.nombre,
                activo=True
            )
            
            # Configurar parámetros específicos por frecuencia
            if frecuencia == 'semanal':
                dias_semana = request.form.getlist('dias_semana[]')
                nueva_programacion.dias_semana = ','.join(dias_semana)
            elif frecuencia == 'mensual':
                dia_mes = request.form.get('dia_mes', 1)
                nueva_programacion.dia_mes = int(dia_mes)
            
            # Calcular próxima ejecución
            nueva_programacion.proxima_ejecucion = nueva_programacion.calcular_proxima_ejecucion()
            
            db.session.add(nueva_programacion)
            db.session.commit()
            
            flash('✅ Programación creada exitosamente', 'success')
            return redirect(url_for('backup.listar_programaciones'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error al crear programación: {str(e)}', 'danger')
    
    return render_template('backups/crear_programacion.html',
                         usb_mounted=detectar_usb_json().get('conectado', False))

@backup_bp.route('/programaciones/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_programacion(id):
    """Editar una programación existente"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden editar programaciones', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    programacion = ProgramacionRespaldo.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            programacion.tipo_respaldo = request.form.get('tipo_respaldo', 'completo')
            programacion.frecuencia = request.form.get('frecuencia', 'diario')
            programacion.almacenamiento = request.form.get('almacenamiento', 'local')
            
            # Actualizar hora
            hora = request.form.get('hora', '02:00')
            programacion.hora_ejecucion = datetime.strptime(hora, '%H:%M').time()
            
            # Actualizar parámetros específicos
            if programacion.frecuencia == 'semanal':
                dias_semana = request.form.getlist('dias_semana[]')
                programacion.dias_semana = ','.join(dias_semana)
                programacion.dia_mes = None
            elif programacion.frecuencia == 'mensual':
                dia_mes = request.form.get('dia_mes', 1)
                programacion.dia_mes = int(dia_mes)
                programacion.dias_semana = None
            else:
                programacion.dias_semana = None
                programacion.dia_mes = None
            
            # Recalcular próxima ejecución
            programacion.proxima_ejecucion = programacion.calcular_proxima_ejecucion()
            
            db.session.commit()
            flash('✅ Programación actualizada exitosamente', 'success')
            return redirect(url_for('backup.listar_programaciones'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error al actualizar programación: {str(e)}', 'danger')
    
    # Convertir días de semana a lista
    dias_semana_lista = []
    if programacion.dias_semana:
        dias_semana_lista = [int(d) for d in programacion.dias_semana.split(',')]
    
    return render_template('backups/editar_programacion.html',
                         programacion=programacion,
                         dias_semana_lista=dias_semana_lista,
                         usb_mounted=detectar_usb_json().get('conectado', False))

@backup_bp.route('/programaciones/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_programacion(id):
    """Activar/desactivar una programación"""
    if current_user.rol != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    programacion = ProgramacionRespaldo.query.get_or_404(id)
    
    try:
        programacion.activo = not programacion.activo
        
        if programacion.activo:
            # Si se activa, recalcular próxima ejecución
            programacion.proxima_ejecucion = programacion.calcular_proxima_ejecucion()
        else:
            # Si se desactiva, limpiar próxima ejecución
            programacion.proxima_ejecucion = None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Programación {"activada" if programacion.activo else "desactivada"}',
            'activo': programacion.activo
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@backup_bp.route('/programaciones/<int:id>/ejecutar-ahora', methods=['POST'])
@login_required
def ejecutar_programacion_ahora(id):
    """Ejecutar una programación inmediatamente"""
    if current_user.rol != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        from app.scheduler import backup_scheduler
        
        if backup_scheduler.ejecutar_ahora(id):
            return jsonify({
                'success': True,
                'message': 'Respaldo programado ejecutado exitosamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se pudo ejecutar la programación'
            }), 400
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@backup_bp.route('/programaciones/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_programacion(id):
    """Eliminar una programación"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden eliminar programaciones', 'danger')
        return redirect(url_for('backup.listar_programaciones'))
    
    programacion = ProgramacionRespaldo.query.get_or_404(id)
    
    try:
        db.session.delete(programacion)
        db.session.commit()
        flash('✅ Programación eliminada exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error al eliminar programación: {str(e)}', 'danger')
    
    return redirect(url_for('backup.listar_programaciones'))