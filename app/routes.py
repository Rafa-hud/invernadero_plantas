# routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import Usuario, Planta, RegistroRiego, Respaldo, HistorialAcceso, Pedido, PedidoDetalle
from datetime import datetime, timedelta, date
import os
import traceback
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
        
        # Login simple para desarrollo
        if correo == 'admin@plantas.com' and contrasenia == 'Admin123!':
            # Buscar usuario admin
            usuario = Usuario.query.filter_by(correo=correo).first()
            
            if not usuario:
                # Crear usuario admin si no existe
                from werkzeug.security import generate_password_hash
                usuario = Usuario(
                    nombre='Administrador',
                    correo=correo,
                    rol='admin'
                )
                usuario.contrasenia_hash = generate_password_hash(contrasenia)
                db.session.add(usuario)
                db.session.commit()
            
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
            return redirect(url_for('main.dashboard'))
        else:
            # Buscar usuario normal en la base de datos
            usuario = Usuario.query.filter_by(correo=correo).first()
            
            if usuario:
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

# ========== MAIN ROUTES ==========
@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def dashboard():
    # Redirigir clientes a la tienda
    if current_user.rol == 'cliente':
        return redirect(url_for('tienda.tienda_index'))
    
    # Estadísticas para el dashboard (solo para admin)
    total_plantas = Planta.query.count()
    
    # Plantas activas
    plantas_activas = Planta.query.filter_by(estado='activa').count()
    
    # Últimos riegos
    ultimos_riegos = RegistroRiego.query.join(Planta)\
        .order_by(RegistroRiego.fecha_riego.desc())\
        .limit(10)\
        .all()
    
    # Último backup
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
    
    # Verificar permisos
    if current_user.rol == 'cliente':
        # Clientes solo pueden ver plantas en venta
        if not planta.disponible_venta or planta.estado != 'activa':
            flash('Planta no disponible', 'danger')
            return redirect(url_for('tienda.tienda_index'))
        return redirect(url_for('tienda.ver_planta_tienda', id=id))
    
    # Admin y usuarios pueden ver todas las plantas
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
            planta.nombre = request.form.get('nombre', '').strip()
            planta.especie = request.form.get('especie', '').strip()
            planta.estado = request.form.get('estado', 'activa')
            planta.precio = float(request.form.get('precio', 0.0))
            planta.stock = int(request.form.get('stock', 0))
            planta.categoria = request.form.get('categoria', '')
            planta.descripcion = request.form.get('descripcion', '')
            planta.disponible_venta = bool(request.form.get('disponible_venta', False))
            
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
    if current_user.rol == 'cliente':
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
    
    planta = Planta.query.get_or_404(id)
    
    if current_user.rol != 'admin' and planta.usuario_id != current_user.id:
        return jsonify({'success': False, 'message': 'No tienes permiso'}), 403
    
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

# ========== TIENDA ONLINE (CLIENTES) ==========
def obtener_carrito():
    """Obtener el carrito de la sesión"""
    if 'carrito' not in session:
        session['carrito'] = {}
    return session['carrito']

def guardar_carrito(carrito):
    """Guardar el carrito en la sesión"""
    session['carrito'] = carrito
    session.modified = True

@tienda_bp.route('/')
@login_required
def tienda_index():
    """Página principal de la tienda para clientes"""
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
            # Actualizar precio si cambió
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
    
    # Calcular totales
    envio = 5.99 if subtotal < 50 else 0  # Envío gratis sobre $50
    iva = subtotal * 0.12  # IVA 12%
    total = subtotal + envio + iva
    
    # Actualizar carrito si hubo cambios
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
        # Verificar que no exceda el stock disponible
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
    
    # Verificar stock antes de proceder
    items_sin_stock = []
    plantas_carrito = []  # Lista para mostrar en el checkout
    subtotal = 0.0
    
    for planta_id, item in carrito.items():
        planta = Planta.query.get(int(planta_id))
        if planta:
            # Verificar stock
            if planta.stock < item['cantidad']:
                items_sin_stock.append({
                    'nombre': planta.nombre,
                    'solicitado': item['cantidad'],
                    'disponible': planta.stock
                })
            
            # Calcular subtotal y agregar a lista de plantas
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
    
    # Calcular totales
    envio = 5.99 if subtotal < 50 else 0
    iva = subtotal * 0.12
    total = subtotal + envio + iva
    
    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            direccion_envio = request.form.get('direccion_envio', '').strip()
            telefono_contacto = request.form.get('telefono_contacto', '').strip()
            notas_pedido = request.form.get('notas_pedido', '').strip()
            metodo_pago = request.form.get('metodo_pago', 'transferencia')
            referencia = request.form.get('referencia', '')
            nombre_cliente = request.form.get('nombre', current_user.nombre)
            
            # Validaciones
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
            
            # Verificar stock nuevamente antes de crear el pedido (para evitar condiciones de carrera)
            for planta_id, item in carrito.items():
                planta = Planta.query.get(int(planta_id))
                if planta and planta.stock < item['cantidad']:
                    flash(f'Lo sentimos, {planta.nombre} ya no tiene suficiente stock. Solo quedan {planta.stock} unidades.', 'danger')
                    return redirect(url_for('tienda.ver_carrito'))
            
            # Crear pedido con los nombres de campo correctos
            nuevo_pedido = Pedido(
                id_cliente=current_user.id,
                costo_total=total,  # Usando el total que ya incluye envío e IVA
                estado_pedido='pendiente',
                fecha_orden=datetime.utcnow()
                # id_pago e id_direccion se llenarán más tarde cuando implementes esos sistemas
            )
            
            db.session.add(nuevo_pedido)
            db.session.flush()  # Obtener el ID del pedido
            
            print(f"Pedido creado con ID: {nuevo_pedido.id_pedido}")
            
            # Crear detalles del pedido
            for planta_id, item in carrito.items():
                planta = Planta.query.get(int(planta_id))
                if planta:
                    # Crear detalle del pedido según tu modelo PedidoDetalle
                    detalle = PedidoDetalle(
                        id_pedido=nuevo_pedido.id_pedido,
                        id_planta=planta.id,
                        cantidad=item['cantidad'],
                        precio_en_compra=float(item['precio'])  # Usando el precio que estaba en el carrito
                    )
                    
                    db.session.add(detalle)
                    
                    # Actualizar stock
                    planta.stock -= item['cantidad']
                    if planta.stock <= 0:
                        planta.disponible_venta = False
                        planta.stock = 0  # Asegurar que no sea negativo
            
            # Confirmar transacción
            db.session.commit()
            
            # Vaciar carrito
            guardar_carrito({})
            
            # Preparar mensaje con los detalles del pedido
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
            print(f"Error completo al procesar pedido: {str(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            flash(f'Error al procesar el pedido: {str(e)}', 'danger')
            return render_template('tienda/checkout.html',
                                 plantas_carrito=plantas_carrito,
                                 subtotal=subtotal,
                                 envio=envio,
                                 iva=iva,
                                 total=total)
    
    # GET request: mostrar formulario de checkout
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
    
    # Usar id_cliente para filtrar según tu modelo
    pedidos = Pedido.query.filter_by(id_cliente=current_user.id)\
        .order_by(Pedido.fecha_orden.desc())\
        .all()
    
    return render_template('tienda/mis_pedidos.html', pedidos=pedidos)

@tienda_bp.route('/pedido/<int:id>')
@login_required
def ver_pedido(id):
    """Ver detalles de un pedido específico"""
    pedido = Pedido.query.get_or_404(id)
    
    # CORREGIDO: usar id_cliente en lugar de usuario_id
    if current_user.rol != 'cliente' or pedido.id_cliente != current_user.id:
        flash('No tienes permiso para ver este pedido', 'danger')
        return redirect(url_for('tienda.mis_pedidos'))
    
    # CORREGIDO: usar id_pedido en lugar de pedido_id
    detalles = PedidoDetalle.query.filter_by(id_pedido=id).all()
    
    # Obtener información completa de las plantas para mostrar
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
    
    # CORREGIDO: usar id_cliente
    if current_user.rol != 'cliente' or pedido.id_cliente != current_user.id:
        flash('No tienes permiso para cancelar este pedido', 'danger')
        return redirect(url_for('tienda.mis_pedidos'))
    
    if pedido.estado_pedido not in ['pendiente', 'procesando']:
        flash('Este pedido no se puede cancelar en su estado actual', 'warning')
        return redirect(url_for('tienda.ver_pedido', id=id))
    
    try:
        # Restaurar stock - CORREGIDO: usar id_pedido
        detalles = PedidoDetalle.query.filter_by(id_pedido=id).all()
        for detalle in detalles:
            planta = Planta.query.get(detalle.id_planta)
            if planta:
                planta.stock += detalle.cantidad
                planta.disponible_venta = True
        
        # Actualizar estado del pedido
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
            # Actualizar información personal
            current_user.nombre = request.form.get('nombre', '').strip()
            current_user.telefono = request.form.get('telefono', '').strip()
            current_user.direccion = request.form.get('direccion', '').strip()
            
            # Actualizar contraseña si se proporciona
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
        pedidos = Pedido.query.order_by(Pedido.fecha_pedido.desc()).all()
    else:
        pedidos = Pedido.query.filter_by(estado=estado)\
            .order_by(Pedido.fecha_pedido.desc())\
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
    detalles = PedidoDetalle.query.filter_by(pedido_id=id).all()
    
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
        pedido.estado = nuevo_estado
        
        # Registrar fecha según el estado
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
    
    # Estadísticas básicas
    total_pedidos = Pedido.query.count()
    pedidos_pendientes = Pedido.query.filter_by(estado='pendiente').count()
    pedidos_procesando = Pedido.query.filter_by(estado='procesando').count()
    
    # Ventas totales
    ventas_totales = db.session.query(db.func.sum(Pedido.total)).scalar() or 0
    
    # Productos más vendidos
    productos_vendidos = db.session.query(
        Planta.nombre,
        db.func.sum(PedidoDetalle.cantidad).label('total_vendido'),
        db.func.sum(PedidoDetalle.total).label('ingresos')
    ).join(PedidoDetalle, Planta.id == PedidoDetalle.planta_id)\
     .group_by(Planta.id)\
     .order_by(db.desc('total_vendido'))\
     .limit(10)\
     .all()
    
    # Ventas por mes (últimos 6 meses)
    seis_meses_atras = datetime.utcnow() - timedelta(days=180)
    ventas_mensuales = db.session.query(
        db.func.strftime('%Y-%m', Pedido.fecha_pedido).label('mes'),
        db.func.count(Pedido.id).label('total_pedidos'),
        db.func.sum(Pedido.total).label('ventas_totales')
    ).filter(Pedido.fecha_pedido >= seis_meses_atras)\
     .group_by('mes')\
     .order_by('mes')\
     .all()
    
    return render_template('admin/estadisticas_tienda.html',
                         total_pedidos=total_pedidos,
                         pedidos_pendientes=pedidos_pendientes,
                         pedidos_procesando=pedidos_procesando,
                         ventas_totales=ventas_totales,
                         productos_vendidos=productos_vendidos,
                         ventas_mensuales=ventas_mensuales)

# ========== CONFIGURACIÓN DE RESPALDOS ==========
BACKUP_FOLDER = 'backups'
ALLOWED_EXTENSIONS = {'sql', 'gz'}

# Asegurar que la carpeta de respaldos existe
if not os.path.exists(BACKUP_FOLDER):
    os.makedirs(BACKUP_FOLDER)

def calcular_checksum(filepath):
    """Calcular checksum SHA-256 de un archivo"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def calcular_tamano_mb(filepath):
    """Calcular tamaño en MB"""
    if os.path.exists(filepath):
        return os.path.getsize(filepath) / (1024 * 1024)
    return 0

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ========== BACKUP ROUTES ==========
@backup_bp.route('/')
@login_required
def listar_respaldos():
    """Listar todos los respaldos disponibles"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden acceder a esta sección', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Obtener respaldos ordenados por fecha descendente
    respaldos = Respaldo.query.order_by(Respaldo.fecha_respaldo.desc()).all()
    
    return render_template('backups/lista.html', respaldos=respaldos)

@backup_bp.route('/crear', methods=['POST'])
@login_required
def crear_respaldo():
    """Crear un nuevo respaldo"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden crear respaldos', 'danger')
        return redirect(url_for('main.dashboard'))
    
    tipo = request.form.get('tipo', 'completo')
    almacenamiento = request.form.get('almacenamiento', 'local')
    
    try:
        # Generar nombre de archivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"respaldo_{tipo}_{timestamp}.sql"
        filepath = os.path.join(BACKUP_FOLDER, filename)
        
        # Configuración de MySQL
        db_host = current_app.config.get('MYSQL_HOST', 'localhost')
        db_user = current_app.config.get('MYSQL_USER', 'root')
        db_password = current_app.config.get('MYSQL_PASSWORD', '')
        db_name = current_app.config.get('MYSQL_DATABASE', 'gestion_plantas')
        
        # Comando para crear respaldo basado en el tipo
        if tipo == 'completo':
            cmd = f"mysqldump -h {db_host} -u {db_user} -p{db_password} {db_name} > {filepath}"
        elif tipo == 'diferencial':
            cmd = f"mysqldump -h {db_host} -u {db_user} -p{db_password} {db_name} plantas registros_riego usuarios > {filepath}"
        else:
            cmd = f"mysqldump -h {db_host} -u {db_user} -p{db_password} {db_name} > {filepath}"
        
        # Ejecutar comando
        result = os.system(cmd)
        
        if result != 0:
            flash('Error al ejecutar mysqldump. Verifica las credenciales de MySQL.', 'danger')
            return redirect(url_for('backup.listar_respaldos'))
        
        # Comprimir archivo
        compressed_filepath = filepath + '.gz'
        with open(filepath, 'rb') as f_in:
            with gzip.open(compressed_filepath, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # Eliminar archivo sin comprimir
        os.remove(filepath)
        
        # Calcular checksum y tamaño
        checksum = calcular_checksum(compressed_filepath)
        tamaño_mb = calcular_tamano_mb(compressed_filepath)
        
        # Registrar respaldo en la base de datos según tu modelo
        nuevo_respaldo = Respaldo(
            tipo_respaldo=tipo,
            ruta_archivo=compressed_filepath,
            tamaño_mb=tamaño_mb,
            realizado_por=current_user.nombre if hasattr(current_user, 'nombre') else 'Sistema',
            almacenamiento=almacenamiento,
            checksum=checksum,
            fecha_respaldo=datetime.now()
        )
        
        db.session.add(nuevo_respaldo)
        db.session.commit()
        
        flash(f'✅ Respaldo {tipo} creado exitosamente ({tamaño_mb:.2f} MB)', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error al crear respaldo: {str(e)}', 'danger')
    
    return redirect(url_for('backup.listar_respaldos'))

@backup_bp.route('/restaurar/<int:id>', methods=['POST'])
@login_required
def restaurar_respaldo(id):
    """Restaurar base de datos desde un respaldo"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden restaurar respaldos', 'danger')
        return redirect(url_for('main.dashboard'))
    
    respaldo = Respaldo.query.get_or_404(id)
    
    try:
        # Verificar integridad del archivo
        if not os.path.exists(respaldo.ruta_archivo):
            flash('❌ El archivo de respaldo no existe', 'danger')
            return redirect(url_for('backup.listar_respaldos'))
        
        # Verificar checksum
        checksum_actual = calcular_checksum(respaldo.ruta_archivo)
        if respaldo.checksum and checksum_actual != respaldo.checksum:
            flash('⚠️ Advertencia: El checksum no coincide. El archivo puede estar corrupto.', 'warning')
        
        # Configuración de MySQL
        db_host = current_app.config.get('MYSQL_HOST', 'localhost')
        db_user = current_app.config.get('MYSQL_USER', 'root')
        db_password = current_app.config.get('MYSQL_PASSWORD', '')
        db_name = current_app.config.get('MYSQL_DATABASE', 'gestion_plantas')
        
        # Comando para restaurar
        if respaldo.ruta_archivo.endswith('.gz'):
            # Descomprimir primero
            temp_file = respaldo.ruta_archivo.replace('.gz', '')
            with gzip.open(respaldo.ruta_archivo, 'rb') as f_in:
                with open(temp_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            cmd = f"mysql -h {db_host} -u {db_user} -p{db_password} {db_name} < {temp_file}"
            result = os.system(cmd)
            os.remove(temp_file)
        else:
            cmd = f"mysql -h {db_host} -u {db_user} -p{db_password} {db_name} < {respaldo.ruta_archivo}"
            result = os.system(cmd)
        
        if result != 0:
            flash('❌ Error al restaurar. Verifica las credenciales de MySQL.', 'danger')
        else:
            flash('✅ Base de datos restaurada exitosamente', 'success')
        
    except Exception as e:
        flash(f'❌ Error al restaurar respaldo: {str(e)}', 'danger')
    
    return redirect(url_for('backup.listar_respaldos'))

@backup_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_respaldo(id):
    """Eliminar un respaldo"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden eliminar respaldos', 'danger')
        return redirect(url_for('main.dashboard'))
    
    respaldo = Respaldo.query.get_or_404(id)
    
    try:
        # Eliminar archivo físico
        if os.path.exists(respaldo.ruta_archivo):
            os.remove(respaldo.ruta_archivo)
        
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
            'archivo': respaldo.ruta_archivo,
            'checksum_original': respaldo.checksum,
            'checksum_actual': checksum_actual,
            'integridad': integridad,
            'tamano_mb': respaldo.tamaño_mb,
            'fecha_creacion': respaldo.fecha_respaldo.strftime('%Y-%m-%d %H:%M:%S')
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
        return redirect(url_for('main.dashboard'))
    
    if 'archivo_respaldo' not in request.files:
        flash('No se seleccionó ningún archivo', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    file = request.files['archivo_respaldo']
    tipo_importacion = request.form.get('tipo_importacion', 'completo')
    
    if file.filename == '':
        flash('Nombre de archivo vacío', 'danger')
        return redirect(url_for('backup.listar_respaldos'))
    
    if file and allowed_file(file.filename):
        try:
            # Guardar archivo temporalmente
            filename = secure_filename(file.filename)
            temp_path = os.path.join(BACKUP_FOLDER, filename)
            file.save(temp_path)
            
            # Configuración de MySQL
            db_host = current_app.config.get('MYSQL_HOST', 'localhost')
            db_user = current_app.config.get('MYSQL_USER', 'root')
            db_password = current_app.config.get('MYSQL_PASSWORD', '')
            db_name = current_app.config.get('MYSQL_DATABASE', 'gestion_plantas')
            
            # Ejecutar importación
            if filename.endswith('.gz'):
                # Descomprimir
                import_file = temp_path.replace('.gz', '')
                with gzip.open(temp_path, 'rb') as f_in:
                    with open(import_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(temp_path)
                
                cmd = f"mysql -h {db_host} -u {db_user} -p{db_password} {db_name} < {import_file}"
                result = os.system(cmd)
                os.remove(import_file)
            else:
                cmd = f"mysql -h {db_host} -u {db_user} -p{db_password} {db_name} < {temp_path}"
                result = os.system(cmd)
                os.remove(temp_path)
            
            if result != 0:
                flash('❌ Error al importar el respaldo. Verifica el formato del archivo.', 'danger')
                return redirect(url_for('backup.listar_respaldos'))
            
            # Registrar el respaldo importado
            checksum = calcular_checksum(temp_path) if os.path.exists(temp_path) else ''
            tamaño_mb = calcular_tamano_mb(temp_path) if os.path.exists(temp_path) else 0
            
            nuevo_respaldo = Respaldo(
                tipo_respaldo=f"importado_{tipo_importacion}",
                ruta_archivo=filename,
                tamaño_mb=tamaño_mb,
                realizado_por=current_user.nombre if hasattr(current_user, 'nombre') else 'Sistema',
                almacenamiento='local',
                checksum=checksum,
                fecha_respaldo=datetime.now()
            )
            
            db.session.add(nuevo_respaldo)
            db.session.commit()
            
            flash('✅ Respaldo importado y restaurado exitosamente', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error al importar respaldo: {str(e)}', 'danger')
    else:
        flash('❌ Tipo de archivo no permitido. Use .sql o .gz', 'danger')
    
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
    
    # Generar reporte simple de respaldos
    respaldos = Respaldo.query.all()
    data = {
        'total': len(respaldos),
        'por_tipo': {},
        'ultimos_meses': []
    }
    
    for respaldo in respaldos:
        # Contar por tipo
        tipo = respaldo.tipo_respaldo
        data['por_tipo'][tipo] = data['por_tipo'].get(tipo, 0) + 1
    
    return jsonify(data)

@reports_bp.route('/accesos')
@login_required
def reporte_accesos():
    if current_user.rol != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    # Generar reporte simple de accesos
    accesos = HistorialAcceso.query.order_by(HistorialAcceso.fecha_acceso.desc()).limit(100).all()
    
    data = {
        'total': len(accesos),
        'por_estado': {},
        'ultimos_accesos': []
    }
    
    for acceso in accesos:
        # Contar por estado
        estado = acceso.estado_sesion
        data['por_estado'][estado] = data['por_estado'].get(estado, 0) + 1
        
        # Agregar a últimos accesos
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
    
    # Generar reporte de ventas
    pedidos = Pedido.query.all()
    
    ventas_por_mes = {}
    productos_mas_vendidos = {}
    
    for pedido in pedidos:
        mes = pedido.fecha_pedido.strftime('%Y-%m')
        ventas_por_mes[mes] = ventas_por_mes.get(mes, 0) + float(pedido.total)
    
    return jsonify({
        'ventas_totales': sum(float(p.total) for p in pedidos),
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
        total_compras = db.session.query(db.func.sum(Pedido.total))\
            .filter(Pedido.usuario_id == cliente.id)\
            .scalar() or 0
        
        total_pedidos = Pedido.query.filter_by(usuario_id=cliente.id).count()
        
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
    
    # Ocultar datos sensibles
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