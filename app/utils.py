import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import gzip
import schedule
import time
import threading
from bson import json_util, ObjectId
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

from app.database import get_db

logger = logging.getLogger(__name__)

class BackupManager:
    def __init__(self, app=None):
        self.app = app
        self.backup_dir = None
        
    def init_app(self, app):
        self.app = app
        self.backup_dir = app.config.get('BACKUP_DIR', 'backups')
        
        # Crear directorio de backups si no existe
        Path(self.backup_dir).mkdir(parents=True, exist_ok=True)
        
        # Iniciar scheduler en un hilo separado
        self.start_scheduler()
    
    def create_backup(self, backup_type='completo', realizado_por='Sistema'):
        """Crea un respaldo de la base de datos MongoDB"""
        
        from app import create_app
        
        if not self.app:
            self.app = create_app()
        
        with self.app.app_context():
            # Generar nombre de archivo
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"backup_{backup_type}_{timestamp}.json.gz"
            filepath = os.path.join(self.backup_dir, filename)
            
            try:
                db = get_db()
                
                # Extraer todas las colecciones
                data_to_backup = {}
                for coll_name in db.list_collection_names():
                    data_to_backup[coll_name] = list(db[coll_name].find())
                
                # Convertir a JSON seguro para BSON y comprimir
                json_data = json_util.dumps(data_to_backup)
                with gzip.open(filepath, 'wt', encoding='utf-8') as f_out:
                    f_out.write(json_data)
                
                # Calcular tamaño y checksum
                tamaño = os.path.getsize(filepath) / (1024 * 1024)  # MB
                checksum = self.calculate_checksum(filepath)
                
                # Guardar en base de datos
                nuevo_respaldo = {
                    'fecha_respaldo': datetime.utcnow(),
                    'tipo_respaldo': backup_type,
                    'ruta_archivo': filepath,
                    'tamaño_mb': round(tamaño, 2),
                    'realizado_por': realizado_por,
                    'almacenamiento': 'local',
                    'checksum': checksum
                }
                
                db.backups.insert_one(nuevo_respaldo)
                
                # Subir a Google Drive si está configurado
                if self.app.config.get('GOOGLE_DRIVE_FOLDER_ID'):
                    self.upload_to_drive(filepath, filename)
                
                logger.info(f"Backup creado: {filename} ({tamaño:.2f} MB)")
                return filepath
                
            except Exception as e:
                logger.error(f"Error al crear backup: {str(e)}")
                raise
    
    def restore_backup(self, backup_path):
        """Restaura la base de datos desde un respaldo JSON.gz"""
        
        if not os.path.exists(backup_path):
            raise Exception("Archivo de respaldo no encontrado")
        
        try:
            with gzip.open(backup_path, 'rt', encoding='utf-8') as f_in:
                backup_data = json_util.loads(f_in.read())
            
            db = get_db()
            for coll_name, documentos in backup_data.items():
                if documentos:
                    # Limpiar la colección antes de restaurar
                    db[coll_name].delete_many({})
                    # Insertar los documentos
                    db[coll_name].insert_many(documentos)
            
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
            
            # Cambiado el mimetype a gzip
            media = MediaFileUpload(filepath, mimetype='application/gzip')
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            # Actualizar registro en MongoDB
            with self.app.app_context():
                db = get_db()
                db.backups.update_one(
                    {'ruta_archivo': filepath},
                    {'$set': {
                        'almacenamiento': 'local,google_drive',
                        'ruta_archivo': f"{filepath}::drive:{file.get('id')}"
                    }}
                )
            
            logger.info(f"Archivo subido a Google Drive: {file.get('id')}")
            
        except Exception as e:
            logger.error(f"Error al subir a Google Drive: {str(e)}")
    
    def cleanup_old_backups(self):
        """Elimina respaldos antiguos según política de retención"""
        retention_days = self.app.config.get('BACKUP_RETENTION_DAYS', 30)
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        with self.app.app_context():
            db = get_db()
            # Buscar respaldos locales más antiguos que la fecha de corte
            old_backups = list(db.backups.find({
                'fecha_respaldo': {'$lt': cutoff_date},
                'almacenamiento': {'$regex': 'local'}
            }))
            
            for backup in old_backups:
                try:
                    ruta_real = backup['ruta_archivo'].split('::')[0]
                    if os.path.exists(ruta_real):
                        os.remove(ruta_real)
                    
                    db.backups.delete_one({'_id': backup['_id']})
                    logger.info(f"Backup eliminado: {backup['ruta_archivo']}")
                except Exception as e:
                    logger.error(f"Error al eliminar backup: {str(e)}")
    
    def start_scheduler(self):
        """Inicia el scheduler interno para backups automáticos"""
        def job_loop():
            while True:
                schedule.run_pending()
                time.sleep(60)
        
        schedule.every().day.at("02:00").do(self.create_incremental_backup)
        schedule.every().sunday.at("03:00").do(self.create_differential_backup)
        schedule.every(15).days.at("04:00").do(self.create_full_backup)
        schedule.every().day.at("05:00").do(self.cleanup_old_backups)
        
        thread = threading.Thread(target=job_loop, daemon=True)
        thread.start()
        logger.info("Scheduler de backups (utils) iniciado")
    
    def create_incremental_backup(self):
        try:
            self.create_backup('minima_modificacion', 'Sistema (automático)')
        except Exception as e:
            self.send_alert_email(f"Error en backup incremental: {str(e)}")
    
    def create_differential_backup(self):
        try:
            self.create_backup('diferencial', 'Sistema (automático)')
        except Exception as e:
            self.send_alert_email(f"Error en backup diferencial: {str(e)}")
    
    def create_full_backup(self):
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
            
            if not username or not password:
                return
            
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
    """Genera reportes del sistema extrayendo datos de MongoDB"""
    
    @staticmethod
    def generate_backup_report():
        """Genera reporte de respaldos"""
        db = get_db()
        respaldos = list(db.backups.find().sort("fecha_respaldo", -1).limit(100))
        
        data = {
            'total': len(respaldos),
            'por_tipo': {},
            'ultimo_mes': [],
            'tamaño_total': 0
        }
        
        hace_un_mes = datetime.utcnow() - timedelta(days=30)
        
        for r in respaldos:
            tipo = r.get('tipo_respaldo', 'desconocido')
            if tipo not in data['por_tipo']:
                data['por_tipo'][tipo] = 0
            data['por_tipo'][tipo] += 1
            
            tamaño = r.get('tamaño_mb', 0)
            data['tamaño_total'] += tamaño
            
            fecha = r.get('fecha_respaldo')
            if fecha and fecha > hace_un_mes:
                data['ultimo_mes'].append({
                    'fecha': fecha.strftime('%Y-%m-%d %H:%M'),
                    'tipo': tipo,
                    'tamaño': tamaño,
                    'realizado_por': r.get('realizado_por', 'Sistema')
                })
        
        return data
    
    @staticmethod
    def generate_access_report():
        """Genera reporte de accesos"""
        db = get_db()
        accesos = list(db.access_logs.find().sort("fecha_acceso", -1).limit(500))
        
        data = {
            'total': len(accesos),
            'por_estado': {},
            'por_usuario': {},
            'ultimos_accesos': []
        }
        
        for a in accesos:
            estado = a.get('estado_sesion', 'desconocido')
            if estado not in data['por_estado']:
                data['por_estado'][estado] = 0
            data['por_estado'][estado] += 1
            
            # Buscar nombre de usuario
            usuario = db.users.find_one({'_id': a.get('usuario_id')})
            usuario_nombre = usuario.get('nombre') if usuario else 'Desconocido'
            
            if usuario_nombre not in data['por_usuario']:
                data['por_usuario'][usuario_nombre] = 0
            data['por_usuario'][usuario_nombre] += 1
            
            fecha = a.get('fecha_acceso')
            fecha_str = fecha.strftime('%Y-%m-%d %H:%M') if fecha else 'N/A'
            
            data['ultimos_accesos'].append({
                'fecha': fecha_str,
                'usuario': usuario_nombre,
                'ip': a.get('ip_address', ''),
                'estado': estado,
                'accion': a.get('accion', '')
            })
        
        return data

# Instancias globales
backup_manager = BackupManager()
report_generator = ReportGenerator()