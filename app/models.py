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
    rol = db.Column(db.String(20), default='cliente')  # 'cliente' o 'admin'
    telefono = db.Column(db.String(20))
    direccion = db.Column(db.Text)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.String(20), default='activo')
    
    # Campos adicionales para clientes
    fecha_nacimiento = db.Column(db.Date)
    genero = db.Column(db.String(10))
    preferencias = db.Column(db.Text)  # JSON con preferencias del cliente
    
    # Relaciones
    plantas = db.relationship('Planta', backref='usuario', lazy=True)
    respaldos = db.relationship('Respaldo', backref='usuario', lazy=True)
    
    # Método para verificar contraseña
    def verificar_contrasenia(self, contrasenia):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.contrasenia_hash, contrasenia)
    
    def __repr__(self):
        return f'<Usuario {self.nombre} ({self.rol})>'


class Planta(db.Model):
    __tablename__ = 'plantas'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    especie = db.Column(db.String(100))
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.String(20), default='activa')
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    
    # Campos para tienda
    precio = db.Column(db.Float, default=0.0)
    descripcion = db.Column(db.Text)
    disponible_venta = db.Column(db.Boolean, default=False)
    stock = db.Column(db.Integer, default=0)
    categoria = db.Column(db.String(50))
    imagen_url = db.Column(db.String(255))
    
    # Relaciones
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
    fecha_respaldo = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    tipo_respaldo = db.Column(db.Enum('completo', 'diferencial', 'minima_modificacion'), 
                             nullable=False)
    ruta_archivo = db.Column(db.String(500), nullable=False)
    tamaño_mb = db.Column(db.Float)
    realizado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    almacenamiento = db.Column(db.String(50))
    checksum = db.Column(db.String(64))
    
    
    
    def __repr__(self):
        return f'<Respaldo {self.tipo_respaldo} - {self.fecha_respaldo}>'

class HistorialAcceso(db.Model):
    __tablename__ = 'historial_accesos'
    
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    fecha_acceso = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    estado_sesion = db.Column(db.Enum('exitoso', 'fallido', 'cerrada'), default='exitoso')
    accion = db.Column(db.String(100))
    
    def __repr__(self):
        return f'<Acceso {self.usuario_id} - {self.estado_sesion}>'

# Configuración de login manager
@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))