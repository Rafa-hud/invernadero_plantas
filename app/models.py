# models.py
from datetime import datetime
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
    imagen_url = db.Column(db.String(255))
    
    # Relación con riegos
    riegos = db.relationship('RegistroRiego', backref='planta', lazy=True)
    
    def __repr__(self):
        return f'<Planta {self.nombre}>'


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

# Configuración de login manager
@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))