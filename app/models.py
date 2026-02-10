# models.py
from datetime import datetime
import os  # AÑADE ESTA IMPORTACIÓN
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
import logging

logger = logging.getLogger(__name__)


class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(100), unique=True, nullable=False)
    contrasenia_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), default='usuario')
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.String(20), default='activo')
    
    # Relación con plantas
    plantas = db.relationship('Planta', backref='usuario', lazy=True)
    
    def set_password(self, password):
        self.contrasenia_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.contrasenia_hash, password)

    def __repr__(self):
        return f'<Usuario {self.id}: {self.nombre}>'


class Pedido(db.Model):
    __tablename__ = 'pedidos'
    
    id_pedido = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    id_pago = db.Column(db.Integer)  # Se llenará después del pago
    id_direccion = db.Column(db.Integer)  # Se llenará con la dirección de envío
    estado_pedido = db.Column(db.String(50), default='pendiente')  # pendiente, procesando, enviado, entregado, cancelado
    fecha_orden = db.Column(db.DateTime, default=datetime.utcnow)
    costo_total = db.Column(db.Float, default=0.0)
    
    # Relaciones
    cliente = db.relationship('Usuario', backref='pedidos')
    detalles = db.relationship('PedidoDetalle', backref='pedido', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Pedido {self.id_pedido} - {self.estado_pedido}>'


class PedidoDetalle(db.Model):
    __tablename__ = 'pedido_detalle'
    
    id_detalle = db.Column(db.Integer, primary_key=True)
    id_pedido = db.Column(db.Integer, db.ForeignKey('pedidos.id_pedido'), nullable=False)
    id_planta = db.Column(db.Integer, db.ForeignKey('plantas.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    precio_en_compra = db.Column(db.Float, nullable=False)
    
    # Relaciones
    planta = db.relationship('Planta', backref='detalles_pedido')
    
    def __repr__(self):
        return f'<PedidoDetalle {self.id_detalle} - {self.cantidad}x Planta {self.id_planta}>'


class Planta(db.Model):
    __tablename__ = 'plantas'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    especie = db.Column(db.String(100))
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.String(20), default='activa')
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    
    # ===== CAMPOS PARA TIENDA =====
    precio = db.Column(db.Float, default=0.0)
    descripcion = db.Column(db.Text)
    disponible_venta = db.Column(db.Boolean, default=False)
    stock = db.Column(db.Integer, default=0)
    categoria = db.Column(db.String(50))
    
    # ===== IMAGEN - CAMPOS REALES (NO propiedades) =====
    imagen_url = db.Column(db.String(500), nullable=True)  # Para URLs externas
    imagen_nombre = db.Column(db.String(255), nullable=True)  # Nombre del archivo local
    imagen_path = db.Column(db.String(500), nullable=True)  # Ruta relativa local
    
    # Relación con riegos
    riegos = db.relationship('RegistroRiego', backref='planta', lazy=True, cascade='all, delete-orphan')
    
    # ===== MÉTODOS PARA MANEJO DE IMÁGENES =====
    
    @property
    def tiene_imagen(self):
        """Verificar si la planta tiene cualquier tipo de imagen"""
        return bool(self.imagen_url or self.imagen_path)
    
    def obtener_imagen(self):
        """Obtener URL completa de la imagen"""
        if self.imagen_url:
            # Si es URL externa, devolverla tal cual
            if self.imagen_url.startswith(('http://', 'https://')):
                return self.imagen_url
            # Si es ruta local en imagen_url, convertir a URL estática
            elif self.imagen_url.startswith('uploads/'):
                return f'/static/{self.imagen_url}'
            # Si es solo nombre de archivo
            else:
                return f'/static/uploads/plantas/{self.imagen_url}'
        elif self.imagen_path:
            # Usar imagen_path como fuente principal para imágenes locales
            return f'/static/{self.imagen_path}'
        
        # Fallback: imagen por defecto
        return '/static/images/planta_default.png'
    
    def es_imagen_local(self):
        """Verificar si la imagen es local (archivo subido)"""
        return bool(self.imagen_path and not self.imagen_url)
    
    def es_imagen_externa(self):
        """Verificar si la imagen es una URL externa"""
        return bool(self.imagen_url and self.imagen_url.startswith(('http://', 'https://')))
    
    def obtener_nombre_imagen(self):
        """Obtener nombre del archivo de imagen"""
        if self.imagen_nombre:
            return self.imagen_nombre
        elif self.imagen_path:
            return os.path.basename(self.imagen_path)
        elif self.imagen_url:
            if self.es_imagen_externa():
                try:
                    return os.path.basename(self.imagen_url.split('?')[0])
                except:
                    return 'imagen_externa.jpg'
            else:
                return os.path.basename(self.imagen_url)
        return None
    
    def obtener_ruta_absoluta(self, app=None):
        """Obtener ruta absoluta del archivo de imagen en el servidor"""
        if not self.es_imagen_local():
            return None
        
        try:
            if app is None:
                from flask import current_app
                app = current_app
            
            # Usar imagen_path como fuente principal
            if self.imagen_path:
                ruta_relativa = self.imagen_path
            elif self.imagen_url and not self.es_imagen_externa():
                ruta_relativa = self.imagen_url
            else:
                return None
            
            # Construir ruta absoluta
            ruta_absoluta = os.path.join(app.root_path, 'static', ruta_relativa)
            
            # Verificar que existe
            if os.path.exists(ruta_absoluta):
                return ruta_absoluta
            
            # Intentar con ubicación alternativa
            if self.imagen_nombre:
                ruta_alternativa = os.path.join(
                    app.root_path, 
                    'static', 
                    'uploads', 
                    'plantas', 
                    self.imagen_nombre
                )
                if os.path.exists(ruta_alternativa):
                    return ruta_alternativa
            
            return None
        except Exception as e:
            logger.error(f"Error obteniendo ruta absoluta: {e}")
            return None
    
    def eliminar_imagen_local(self, app=None):
        """Eliminar archivo de imagen local del servidor"""
        try:
            if not self.es_imagen_local():
                return False
            
            ruta_absoluta = self.obtener_ruta_absoluta(app)
            if ruta_absoluta and os.path.exists(ruta_absoluta):
                os.remove(ruta_absoluta)
                logger.info(f"Imagen eliminada: {ruta_absoluta}")
                return True
            
            # Si no se pudo encontrar pero hay nombre de archivo,
            # intentar eliminar desde la carpeta por defecto
            if self.imagen_nombre:
                if app is None:
                    from flask import current_app
                    app = current_app
                
                upload_folder = app.config.get('PLANTAS_UPLOAD_FOLDER', 
                                             os.path.join('static', 'uploads', 'plantas'))
                ruta_por_defecto = os.path.join(upload_folder, self.imagen_nombre)
                
                if os.path.exists(ruta_por_defecto):
                    os.remove(ruta_por_defecto)
                    logger.info(f"Imagen eliminada (ubicación por defecto): {ruta_por_defecto}")
                    return True
            
            return False
        except Exception as e:
            logger.error(f"Error eliminando imagen: {e}")
            return False
    
    def actualizar_imagen_local(self, filename, app=None):
        """Actualizar imagen local con nuevo archivo"""
        try:
            # 1. Eliminar imagen anterior si existe
            self.eliminar_imagen_local(app)
            
            # 2. Actualizar campos de imagen
            self.imagen_nombre = filename
            self.imagen_path = f'uploads/plantas/{filename}'
            self.imagen_url = None  # Limpiar URL externa
            
            return True
        except Exception as e:
            logger.error(f"Error actualizando imagen local: {e}")
            return False
    
    def actualizar_imagen_url(self, url):
        """Actualizar con URL externa"""
        try:
            # Eliminar imagen local si existe
            if self.es_imagen_local():
                self.eliminar_imagen_local()
            
            # Actualizar campos
            self.imagen_url = url
            self.imagen_nombre = None
            self.imagen_path = None
            
            return True
        except Exception as e:
            logger.error(f"Error actualizando imagen URL: {e}")
            return False
    
    def limpiar_imagen(self, app=None):
        """Limpiar completamente la imagen (eliminar archivo y campos)"""
        try:
            if self.es_imagen_local():
                self.eliminar_imagen_local(app)
            
            self.imagen_url = None
            self.imagen_nombre = None
            self.imagen_path = None
            
            return True
        except Exception as e:
            logger.error(f"Error limpiando imagen: {e}")
            return False
    
    def obtener_info_imagen(self):
        """Obtener información detallada de la imagen"""
        return {
            'tiene_imagen': self.tiene_imagen,
            'es_local': self.es_imagen_local(),
            'es_externa': self.es_imagen_externa(),
            'url': self.obtener_imagen(),
            'nombre': self.obtener_nombre_imagen(),
            'ruta_relativa': self.imagen_path,
            'url_externa': self.imagen_url if self.es_imagen_externa() else None
        }
    
    def to_dict(self, incluir_imagen=True):
        """Convertir planta a diccionario (útil para APIs)"""
        data = {
            'id': self.id,
            'nombre': self.nombre,
            'especie': self.especie,
            'estado': self.estado,
            'precio': float(self.precio) if self.precio else 0.0,
            'descripcion': self.descripcion,
            'disponible_venta': self.disponible_venta,
            'stock': self.stock,
            'categoria': self.categoria,
            'usuario_id': self.usuario_id,
            'fecha_registro': self.fecha_registro.isoformat() if self.fecha_registro else None,
        }
        
        if incluir_imagen:
            data['imagen'] = self.obtener_info_imagen()
        
        return data
    
    # ===== MÉTODOS DE VALIDACIÓN =====
    
    def validar_antes_de_guardar(self):
        """Validar datos antes de guardar en la base de datos"""
        errores = []
        
        if not self.nombre or len(self.nombre.strip()) < 2:
            errores.append("El nombre debe tener al menos 2 caracteres")
        
        if self.precio < 0:
            errores.append("El precio no puede ser negativo")
        
        if self.stock < 0:
            errores.append("El stock no puede ser negativo")
        
        # Validar que no tenga ambos tipos de imagen
        if self.imagen_url and self.imagen_path:
            errores.append("No se pueden tener URL externa y archivo local simultáneamente")
        
        return errores
    
    # ===== MÉTODOS DE NEGOCIO =====
    
    def reducir_stock(self, cantidad):
        """Reducir el stock de la planta"""
        if cantidad <= 0:
            return False, "Cantidad debe ser mayor a 0"
        
        if self.stock < cantidad:
            return False, f"Stock insuficiente. Disponible: {self.stock}"
        
        self.stock -= cantidad
        
        # Si stock llega a 0, marcar como no disponible para venta
        if self.stock == 0 and self.disponible_venta:
            self.disponible_venta = False
        
        return True, f"Stock reducido exitosamente. Nuevo stock: {self.stock}"
    
    def aumentar_stock(self, cantidad):
        """Aumentar el stock de la planta"""
        if cantidad <= 0:
            return False, "Cantidad debe ser mayor a 0"
        
        self.stock += cantidad
        
        # Si tenía stock 0 y ahora tiene, marcar como disponible
        if self.stock > 0 and not self.disponible_venta:
            self.disponible_venta = True
        
        return True, f"Stock aumentado exitosamente. Nuevo stock: {self.stock}"
    
    def puede_venderse(self):
        """Verificar si la planta puede venderse"""
        return self.disponible_venta and self.stock > 0 and self.estado == 'activa'
    
    def __repr__(self):
        return f'<Planta {self.id}: {self.nombre}>'


class RegistroRiego(db.Model):
    __tablename__ = 'registros_riego'
    
    id = db.Column(db.Integer, primary_key=True)
    id_planta = db.Column(db.Integer, db.ForeignKey('plantas.id'), nullable=False)
    fecha_riego = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    cantidad_agua = db.Column(db.Integer, nullable=False)
    tipo_riego = db.Column(db.String(50), default='normal')
    notas = db.Column(db.Text)
    
    def __repr__(self):
        return f'<RegistroRiego {self.id} - Planta {self.id_planta}>'


class Respaldo(db.Model):
    __tablename__ = 'respaldos'
    
    id = db.Column(db.Integer, primary_key=True)
    tipo_respaldo = db.Column(db.String(50))
    ruta_archivo = db.Column(db.String(255))
    fecha_respaldo = db.Column(db.DateTime, default=datetime.utcnow)
    tamaño_mb = db.Column(db.Float)
    realizado_por = db.Column(db.String(100))
    almacenamiento = db.Column(db.String(50))
    checksum = db.Column(db.String(64))
    
    def __repr__(self):
        return f'<Respaldo {self.tipo_respaldo} - {self.fecha_respaldo}>'


class HistorialAcceso(db.Model):
    __tablename__ = 'historial_accesos'
    
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    fecha_acceso = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    estado_sesion = db.Column(db.String(20))
    accion = db.Column(db.String(50))
    
    def __repr__(self):
        return f'<HistorialAcceso {self.usuario_id} - {self.fecha_acceso}>'


class ProgramacionRespaldo(db.Model):
    __tablename__ = 'programaciones_respaldos'
    
    id = db.Column(db.Integer, primary_key=True)
    tipo_respaldo = db.Column(db.String(50), nullable=False)
    frecuencia = db.Column(db.String(50), nullable=False)
    hora_ejecucion = db.Column(db.Time, nullable=False)
    dias_semana = db.Column(db.String(50))
    dia_mes = db.Column(db.Integer)
    almacenamiento = db.Column(db.String(50), default='local')
    activo = db.Column(db.Boolean, default=True)
    ultima_ejecucion = db.Column(db.DateTime)
    proxima_ejecucion = db.Column(db.DateTime)
    usuario_creador = db.Column(db.String(100))
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ProgramacionRespaldo {self.tipo_respaldo} - {self.frecuencia}>'
    
    def calcular_proxima_ejecucion(self):
        """Calcular próxima fecha de ejecución basada en la programación"""
        from datetime import datetime, timedelta
        
        ahora = datetime.utcnow()
        
        # Si ya tiene próxima ejecución futura, mantenerla
        if self.proxima_ejecucion and self.proxima_ejecucion > ahora:
            return self.proxima_ejecucion
        
        fecha_base = self.ultima_ejecucion or ahora
        
        if self.frecuencia == 'diario':
            hoy_con_hora = datetime.combine(ahora.date(), self.hora_ejecucion)
            if hoy_con_hora > ahora:
                return hoy_con_hora
            else:
                return hoy_con_hora + timedelta(days=1)
        
        elif self.frecuencia == 'semanal':
            dias = [int(d) for d in self.dias_semana.split(',')] if self.dias_semana else [ahora.weekday()]
            
            for i in range(1, 8):
                fecha_candidata = fecha_base + timedelta(days=i)
                if fecha_candidata.weekday() in dias:
                    return datetime.combine(fecha_candidata.date(), self.hora_ejecucion)
            
            return ahora + timedelta(days=1)
        
        elif self.frecuencia == 'mensual':
            dia_mes = self.dia_mes or 1
            
            try:
                proxima_mes = ahora.replace(day=dia_mes)
                if proxima_mes <= ahora:
                    if ahora.month == 12:
                        proxima_mes = proxima_mes.replace(year=ahora.year + 1, month=1)
                    else:
                        proxima_mes = proxima_mes.replace(month=ahora.month + 1)
                return datetime.combine(proxima_mes.date(), self.hora_ejecucion)
            except ValueError:
                # Si el día no es válido para el mes, usar el último día
                ultimo_dia = (ahora.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                return datetime.combine(ultimo_dia.date(), self.hora_ejecucion)
        
        return ahora + timedelta(days=1)


# Configuración de login manager
@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))