import os
import subprocess
import json
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
from app import db
from app.models import Respaldo
import schedule
import time
import threading
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

logger = logging.getLogger(__name__)

class BackupManager:
    def __init__(self, app=None):
        self.app = app
        self.backup_dir = None
        self.db_config = None
        
    def init_app(self, app):
        self.app = app
        self.backup_dir = app.config['BACKUP_DIR']
        self.db_config = app.config['SQLALCHEMY_DATABASE_URI']
        
        # Crear directorio de backups si no existe
        Path(self.backup_dir).mkdir(parents=True, exist_ok=True)
        
        # Iniciar scheduler en un hilo separado
        self.start_scheduler()
    
    def create_backup(self, backup_type='completo', realizado_por='Sistema'):
        """Crea un respaldo de la base de datos"""
        
        from app import create_app
        
        if not self.app:
            self.app = create_app()
        
        with self.app.app_context():
            # Generar nombre de archivo
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"backup_{backup_type}_{timestamp}.sql"
            filepath = os.path.join(self.backup_dir, filename)
            
            # Extraer información de conexión
            # Formato: mysql+mysqlconnector://user:pass@host/dbname
            db_info = self.db_config.replace('mysql+mysqlconnector://', '')
            user_pass, host_db = db_info.split('@')
            user, password = user_pass.split(':')
            host, database = host_db.split('/')
            
            # Comando mysqldump
            cmd = [
                'mysqldump',
                f'-u{user}',
                f'-p{password}',
                f'-h{host}',
                '--skip-comments',
                '--complete-insert',
                '--single-transaction',
                database
            ]
            
            # Ejecutar backup
            try:
                with open(filepath, 'w') as f:
                    result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
                
                if result.returncode != 0:
                    raise Exception(f"Error en mysqldump: {result.stderr}")
                
                # Calcular tamaño y checksum
                tamaño = os.path.getsize(filepath) / (1024 * 1024)  # MB
                checksum = self.calculate_checksum(filepath)
                
                # Guardar en base de datos
                respaldo = Respaldo(
                    fecha_respaldo=datetime.now(),
                    tipo_respaldo=backup_type,
                    ruta_archivo=filepath,
                    tamaño_mb=round(tamaño, 2),
                    realizado_por=realizado_por,
                    almacenamiento='local',
                    checksum=checksum
                )
                db.session.add(respaldo)
                db.session.commit()
                
                # Subir a Google Drive si está configurado
                if self.app.config.get('GOOGLE_DRIVE_FOLDER_ID'):
                    self.upload_to_drive(filepath, filename)
                
                logger.info(f"Backup creado: {filename} ({tamaño:.2f} MB)")
                return filepath
                
            except Exception as e:
                logger.error(f"Error al crear backup: {str(e)}")
                raise
    
    def restore_backup(self, backup_path):
        """Restaura la base de datos desde un respaldo"""
        
        if not os.path.exists(backup_path):
            raise Exception("Archivo de respaldo no encontrado")
        
        # Extraer información de conexión
        db_info = self.db_config.replace('mysql+mysqlconnector://', '')
        user_pass, host_db = db_info.split('@')
        user, password = user_pass.split(':')
        host, database = host_db.split('/')
        
        # Comando mysql para restaurar
        cmd = [
            'mysql',
            f'-u{user}',
            f'-p{password}',
            f'-h{host}',
            database
        ]
        
        try:
            with open(backup_path, 'r') as f:
                result = subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Error al restaurar: {result.stderr}")
            
            logger.info(f"Backup restaurado desde: {backup_path}")
            
        except Exception as e:
            logger.error(f"Error al restaurar backup: {str(e)}")
            raise
    
    def calculate_checksum(self, filepath):
        """Calcula SHA-256 checksum para verificar integridad"""
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def upload_to_drive(self, filepath, filename):
        """Sube archivo a Google Drive"""
        try:
            SCOPES = ['https://www.googleapis.com/auth/drive.file']
            creds_file = self.app.config.get('GOOGLE_CREDENTIALS_FILE')
            
            if not creds_file or not os.path.exists(creds_file):
                logger.warning("Archivo de credenciales de Google Drive no encontrado")
                return
            
            creds = service_account.Credentials.from_service_account_file(
                creds_file, scopes=SCOPES)
            
            service = build('drive', 'v3', credentials=creds)
            
            file_metadata = {
                'name': filename,
                'parents': [self.app.config['GOOGLE_DRIVE_FOLDER_ID']]
            }
            
            media = MediaFileUpload(filepath, mimetype='application/sql')
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            # Actualizar registro con ID de Drive
            respaldo = Respaldo.query.filter_by(ruta_archivo=filepath).first()
            if respaldo:
                respaldo.almacenamiento = 'local,google_drive'
                respaldo.ruta_archivo = f"{filepath}::drive:{file.get('id')}"
                db.session.commit()
            
            logger.info(f"Archivo subido a Google Drive: {file.get('id')}")
            
        except Exception as e:
            logger.error(f"Error al subir a Google Drive: {str(e)}")
    
    def cleanup_old_backups(self):
        """Elimina respaldos antiguos según política de retención"""
        retention_days = self.app.config.get('BACKUP_RETENTION_DAYS', 30)
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        with self.app.app_context():
            old_backups = Respaldo.query.filter(
                Respaldo.fecha_respaldo < cutoff_date,
                Respaldo.almacenamiento.contains('local')
            ).all()
            
            for backup in old_backups:
                try:
                    if os.path.exists(backup.ruta_archivo.split('::')[0]):
                        os.remove(backup.ruta_archivo.split('::')[0])
                    db.session.delete(backup)
                    logger.info(f"Backup eliminado: {backup.ruta_archivo}")
                except Exception as e:
                    logger.error(f"Error al eliminar backup: {str(e)}")
            
            db.session.commit()
    
    def start_scheduler(self):
        """Inicia el scheduler para backups automáticos"""
        
        def job_loop():
            while True:
                schedule.run_pending()
                time.sleep(60)  # Revisar cada minuto
        
        # Programar backups según configuración
        schedule.every().day.at("02:00").do(self.create_incremental_backup)
        schedule.every().sunday.at("03:00").do(self.create_differential_backup)
        schedule.every(15).days.at("04:00").do(self.create_full_backup)
        schedule.every().day.at("05:00").do(self.cleanup_old_backups)
        
        # Iniciar hilo para scheduler
        thread = threading.Thread(target=job_loop, daemon=True)
        thread.start()
        logger.info("Scheduler de backups iniciado")
    
    def create_incremental_backup(self):
        """Crea respaldo de mínima modificación (diario)"""
        try:
            self.create_backup('minima_modificacion', 'Sistema (automático)')
        except Exception as e:
            self.send_alert_email(f"Error en backup incremental: {str(e)}")
    
    def create_differential_backup(self):
        """Crea respaldo diferencial (semanal)"""
        try:
            self.create_backup('diferencial', 'Sistema (automático)')
        except Exception as e:
            self.send_alert_email(f"Error en backup diferencial: {str(e)}")
    
    def create_full_backup(self):
        """Crea respaldo completo (quincenal)"""
        try:
            self.create_backup('completo', 'Sistema (automático)')
        except Exception as e:
            self.send_alert_email(f"Error en backup completo: {str(e)}")
    
    def send_alert_email(self, message):
        """Envía alerta por email"""
        try:
            smtp_server = self.app.config['MAIL_SERVER']
            smtp_port = self.app.config['MAIL_PORT']
            username = self.app.config['MAIL_USERNAME']
            password = self.app.config['MAIL_PASSWORD']
            
            msg = MIMEMultipart()
            msg['From'] = username
            msg['To'] = 'admin@plantas.com'
            msg['Subject'] = 'Alerta - Sistema de Gestión de Plantas'
            
            body = f"""
            ALERTA DEL SISTEMA
            Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            
            Mensaje: {message}
            
            Por favor, verifique el sistema inmediatamente.
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
            server.quit()
            
        except Exception as e:
            logger.error(f"Error al enviar email de alerta: {str(e)}")

class ReportGenerator:
    """Genera reportes del sistema"""
    
    @staticmethod
    def generate_backup_report():
        """Genera reporte de respaldos"""
        from app.models import Respaldo
        
        respaldos = Respaldo.query.order_by(Respaldo.fecha_respaldo.desc()).limit(100).all()
        
        data = {
            'total': len(resaldos),
            'por_tipo': {},
            'ultimo_mes': [],
            'tamaño_total': 0
        }
        
        for r in respaldos:
            # Estadísticas por tipo
            if r.tipo_respaldo not in data['por_tipo']:
                data['por_tipo'][r.tipo_respaldo] = 0
            data['por_tipo'][r.tipo_respaldo] += 1
            
            # Tamaño total
            if r.tamaño_mb:
                data['tamaño_total'] += r.tamaño_mb
            
            # Último mes
            if r.fecha_respaldo > datetime.now() - timedelta(days=30):
                data['ultimo_mes'].append({
                    'fecha': r.fecha_respaldo.strftime('%Y-%m-%d %H:%M'),
                    'tipo': r.tipo_respaldo,
                    'tamaño': r.tamaño_mb,
                    'realizado_por': r.realizado_por
                })
        
        return data
    
    @staticmethod
    def generate_access_report():
        """Genera reporte de accesos"""
        from app.models import HistorialAcceso, Usuario
        
        accesos = HistorialAcceso.query.order_by(
            HistorialAcceso.fecha_acceso.desc()
        ).limit(500).all()
        
        data = {
            'total': len(accesos),
            'por_estado': {},
            'por_usuario': {},
            'ultimos_accesos': []
        }
        
        for a in accesos:
            # Por estado
            if a.estado_sesion not in data['por_estado']:
                data['por_estado'][a.estado_sesion] = 0
            data['por_estado'][a.estado_sesion] += 1
            
            # Por usuario
            usuario = Usuario.query.get(a.usuario_id)
            usuario_nombre = usuario.nombre if usuario else 'Desconocido'
            if usuario_nombre not in data['por_usuario']:
                data['por_usuario'][usuario_nombre] = 0
            data['por_usuario'][usuario_nombre] += 1
            
            # Últimos accesos
            data['ultimos_accesos'].append({
                'fecha': a.fecha_acceso.strftime('%Y-%m-%d %H:%M'),
                'usuario': usuario_nombre,
                'ip': a.ip_address,
                'estado': a.estado_sesion,
                'accion': a.accion
            })
        
        return data

# Instancias globales
backup_manager = BackupManager()
report_generator = ReportGenerator()