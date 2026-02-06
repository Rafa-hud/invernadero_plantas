# routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import Usuario, Planta, RegistroRiego, Respaldo, HistorialAcceso
from datetime import datetime, timedelta, date
import os
import gzip
import shutil
import hashlib
from werkzeug.utils import secure_filename
import json

# Blueprints
auth_bp = Blueprint('auth', __name__)
main_bp = Blueprint('main', __name__)
plants_bp = Blueprint('plants', __name__)
backup_bp = Blueprint('backup', __name__)
reports_bp = Blueprint('reports', __name__)
tienda_bp = Blueprint('tienda', __name__)  # Blueprint para tienda

# ========== AUTH ROUTES ==========
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # Redirigir según el rol
        if current_user.rol == 'admin':
            return redirect(url_for('main.dashboard'))
        elif current_user.rol == 'cliente':
            return redirect(url_for('tienda.tienda_index'))
        else:
            return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        correo = request.form.get('correo')
        contrasenia = request.form.get('contrasenia')
        
        # Buscar usuario en la base de datos
        usuario = Usuario.query.filter_by(correo=correo).first()
        
        if usuario:
            # Verificar contraseña
            from werkzeug.security import check_password_hash
            if check_password_hash(usuario.contrasenia_hash, contrasenia):
                login_user(usuario, remember=True)
                
                # Registrar acceso
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
                
                # Redirigir según el rol
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
    # Registrar cierre de sesión
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

# ========== MAIN ROUTES ==========
@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def dashboard():
    # Estadísticas para el dashboard
    total_plantas = Planta.query.filter_by(usuario_id=current_user.id).count()
    
    # Plantas activas
    plantas_activas = Planta.query.filter(
        Planta.usuario_id == current_user.id,
        Planta.estado == 'activa'
    ).count()
    
    # Últimos riegos
    ultimos_riegos = RegistroRiego.query.join(Planta).filter(
        Planta.usuario_id == current_user.id
    ).order_by(RegistroRiego.fecha_riego.desc()).limit(10).all()
    
    # Último backup (solo para admin)
    ultimo_backup = None
    if current_user.rol == 'admin':
        ultimo_backup = Respaldo.query.order_by(Respaldo.fecha_respaldo.desc()).first()
        if ultimo_backup:
            ultimo_backup = ultimo_backup.fecha_respaldo
    
    return render_template('dashboard.html',
                         total_plantas=total_plantas,
                         plantas_riego_hoy=plantas_activas,
                         ultimos_riegos=ultimos_riegos,
                         ultimo_backup=ultimo_backup)

# ========== PLANTAS ROUTES ==========
@plants_bp.route('/')
@login_required
def listar_plantas():
    plantas = Planta.query.filter_by(usuario_id=current_user.id).all()
    return render_template('plants/lista.html', plantas=plantas)

@plants_bp.route('/crear', methods=['GET', 'POST'])
@login_required
def crear_planta():
    if request.method == 'POST':
        try:
            nombre = request.form.get('nombre', '').strip()
            especie = request.form.get('especie', '').strip()
            
            if not nombre:
                flash('El nombre de la planta es requerido', 'error')
                return render_template('plants/crear.html')
            
            nueva_planta = Planta(
                nombre=nombre,
                especie=especie,
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
    
    if planta.usuario_id != current_user.id and current_user.rol != 'admin':
        flash('No tienes permiso para ver esta planta', 'danger')
        return redirect(url_for('plants.listar_plantas'))
    
    now = datetime.utcnow()
    
    return render_template('plants/detalle.html', planta=planta, now=now)

@plants_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_planta(id):
    planta = Planta.query.get_or_404(id)
    
    if planta.usuario_id != current_user.id and current_user.rol != 'admin':
        flash('No tienes permiso para editar esta planta', 'danger')
        return redirect(url_for('plants.listar_plantas'))
    
    if request.method == 'POST':
        try:
            planta.nombre = request.form.get('nombre', '').strip()
            planta.especie = request.form.get('especie', '').strip()
            planta.estado = request.form.get('estado', 'activa')
            
            db.session.commit()
            flash(f'Planta "{planta.nombre}" actualizada correctamente', 'success')
            return redirect(url_for('plants.detalle_planta', id=planta.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la planta: {str(e)}', 'error')
            return render_template('plants/editar.html', planta=planta)
    
    return render_template('plants/editar.html', planta=planta)

@plants_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_planta(id):
    planta = Planta.query.get_or_404(id)
    
    if planta.usuario_id != current_user.id and current_user.rol != 'admin':
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
    planta = Planta.query.get_or_404(id)
    
    if planta.usuario_id != current_user.id and current_user.rol != 'admin':
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
        
        if planta.usuario_id != current_user.id and current_user.rol != 'admin':
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

# ========== TIENDA ONLINE ROUTES ==========
@tienda_bp.route('/')
@login_required
def tienda_index():
    """Página principal de la tienda para clientes"""
    # Solo clientes pueden acceder
    if current_user.rol != 'cliente':
        flash('Acceso solo para clientes', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Obtener plantas disponibles para venta
    plantas_disponibles = Planta.query.filter_by(
        disponible_venta=True,
        estado='activa'
    ).filter(Planta.stock > 0).all()
    
    # Obtener categorías únicas
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
    
    # Obtener plantas relacionadas (misma categoría)
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
    
    # Construir consulta base
    plantas_query = Planta.query.filter(
        Planta.disponible_venta == True,
        Planta.estado == 'activa',
        Planta.stock > 0
    )
    
    # Aplicar filtros
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
    
    # Obtener categorías para el filtro
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

@tienda_bp.route('/carrito')
@login_required
def ver_carrito():
    """Ver carrito de compras"""
    if current_user.rol != 'cliente':
        flash('Acceso solo para clientes', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # En una implementación real, aquí obtendrías el carrito de la sesión o base de datos
    carrito = []  # Esto sería una lista de items del carrito
    
    return render_template('tienda/carrito.html', carrito=carrito)

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

# ========== BACKUP ROUTES ==========
# (Aquí van las funciones de backup que ya tienes, pero simplificadas)

@backup_bp.route('/')
@login_required
def listar_respaldos():
    if current_user.rol != 'admin':
        flash('Solo administradores pueden acceder a esta sección', 'danger')
        return redirect(url_for('main.dashboard'))
    
    respaldos = Respaldo.query.order_by(Respaldo.fecha_respaldo.desc()).all()
    return render_template('backups/lista.html', respaldos=respaldos)

@backup_bp.route('/crear', methods=['POST'])
@login_required
def crear_respaldo():
    if current_user.rol != 'admin':
        flash('Solo administradores pueden crear respaldos', 'danger')
        return redirect(url_for('main.dashboard'))
    
    tipo = request.form.get('tipo', 'completo')
    
    try:
        # Configuración básica para demo
        backup_info = {
            'tipo': tipo,
            'fecha': datetime.now(),
            'realizado_por': current_user.nombre
        }
        
        # En una implementación real, aquí ejecutarías mysqldump
        flash(f'✅ Respaldo {tipo} creado exitosamente', 'success')
        
    except Exception as e:
        flash(f'❌ Error al crear respaldo: {str(e)}', 'danger')
    
    return redirect(url_for('backup.listar_respaldos'))

# ========== REPORTES ROUTES ==========
@reports_bp.route('/')
@login_required
def reportes():
    if current_user.rol != 'admin':
        flash('Solo administradores pueden ver reportes', 'danger')
        return redirect(url_for('main.dashboard'))
    
    return render_template('reports/index.html')

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


# ========== REGISTRO DE CLIENTES ==========
@auth_bp.route('/registro', methods=['GET', 'POST'])
def registro_cliente():
    """Registro de nuevos clientes"""
    # Si ya está autenticado, redirigir al dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            nombre = request.form.get('nombre', '').strip()
            correo = request.form.get('correo', '').strip().lower()
            contrasenia = request.form.get('contrasenia', '')
            confirmar_contrasenia = request.form.get('confirmar_contrasenia', '')
            telefono = request.form.get('telefono', '').strip()
            direccion = request.form.get('direccion', '').strip()
            
            # Validaciones
            errores = []
            
            if not nombre or len(nombre) < 3:
                errores.append('El nombre debe tener al menos 3 caracteres.')
            
            if not correo or '@' not in correo:
                errores.append('Correo electrónico inválido.')
            
            # Verificar que el correo no exista
            usuario_existente = Usuario.query.filter_by(correo=correo).first()
            if usuario_existente:
                errores.append('Este correo ya está registrado.')
            
            if not contrasenia or len(contrasenia) < 6:
                errores.append('La contraseña debe tener al menos 6 caracteres.')
            
            if contrasenia != confirmar_contrasenia:
                errores.append('Las contraseñas no coinciden.')
            
            # Si hay errores, mostrar todos
            if errores:
                for error in errores:
                    flash(error, 'danger')
                return render_template('auth/registro.html',
                                     nombre=nombre,
                                     correo=correo,
                                     telefono=telefono,
                                     direccion=direccion)
            
            # Crear nuevo usuario cliente
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
            
            # Guardar en la base de datos
            db.session.add(nuevo_cliente)
            db.session.commit()
            
            # Registrar acceso
            acceso = HistorialAcceso(
                usuario_id=nuevo_cliente.id,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string,
                estado_sesion='registro',
                accion='registro_cliente'
            )
            db.session.add(acceso)
            db.session.commit()
            
            # Autenticar automáticamente
            login_user(nuevo_cliente, remember=True)
            
            flash('¡Registro exitoso! Bienvenido/a a nuestra tienda.', 'success')
            return redirect(url_for('tienda.tienda_index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error en el registro: {str(e)}', 'danger')
            return render_template('auth/registro.html')
    
    # GET request: mostrar formulario vacío
    return render_template('auth/registro.html')

@auth_bp.route('/registro-exitoso')
@login_required
def registro_exitoso():
    """Página de registro exitoso"""
    return render_template('auth/registro_exitoso.html')


# ========== RUTAS PARA GESTIONAR TIENDA ==========

@plants_bp.route('/<int:id>/agregar-tienda', methods=['POST'])
@login_required
def agregar_a_tienda(id):
    """Agregar una planta a la tienda online"""
    planta = Planta.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Actualizar campos para la tienda
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
    planta = Planta.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Actualizar campos
            planta.precio = float(request.form.get('precio', 0))
            planta.stock = int(request.form.get('stock', 0))
            
            # Manejar disponible_venta
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