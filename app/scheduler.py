# app/scheduler.py
import threading
import time
from datetime import datetime, timedelta
from app import create_app, db
from app.models import ProgramacionRespaldo, Respaldo
import logging
import traceback
import os
import subprocess
import gzip
import shutil

logger = logging.getLogger(__name__)

class BackupScheduler:
    def __init__(self):
        self.app = None
        self.running = False
        self.thread = None
        self.check_interval = 60  # Segundos entre verificaciones
        
    def start(self, app_instance=None):
        """Iniciar el planificador"""
        if self.running:
            logger.warning("Planificador ya está en ejecución")
            return
        
        if app_instance:
            self.app = app_instance
        else:
            self.app = create_app()
        
        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info("Planificador de respaldos iniciado")
    
    def stop(self):
        """Detener el planificador"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Planificador de respaldos detenido")
    
    def _run_scheduler(self):
        """Bucle principal del planificador"""
        with self.app.app_context():
            while self.running:
                try:
                    self._check_scheduled_backups()
                except Exception as e:
                    logger.error(f"Error en planificador: {e}")
                    logger.error(traceback.format_exc())
                
                # Esperar antes de la siguiente verificación
                for _ in range(self.check_interval):
                    if not self.running:
                        break
                    time.sleep(1)
    
    def _check_scheduled_backups(self):
        """Verificar y ejecutar respaldos programados"""
        ahora = datetime.utcnow()
        
        # Obtener programaciones activas
        programaciones = ProgramacionRespaldo.query.filter_by(activo=True).all()
        
        for programacion in programaciones:
            try:
                # Verificar si es hora de ejecutar
                if not programacion.proxima_ejecucion:
                    programacion.proxima_ejecucion = programacion.calcular_proxima_ejecucion()
                    db.session.commit()
                
                # Verificar si la próxima ejecución ya pasó
                if programacion.proxima_ejecucion and programacion.proxima_ejecucion <= ahora:
                    logger.info(f"Ejecutando respaldo programado #{programacion.id} - {programacion.tipo_respaldo}")
                    
                    # Ejecutar el respaldo
                    self._execute_scheduled_backup(programacion)
                    
                    # Actualizar fechas de ejecución
                    programacion.ultima_ejecucion = ahora
                    programacion.proxima_ejecucion = programacion.calcular_proxima_ejecucion()
                    db.session.commit()
                    
                    logger.info(f"Respaldo programado #{programacion.id} completado. Próxima ejecución: {programacion.proxima_ejecucion}")
                    
            except Exception as e:
                logger.error(f"Error ejecutando programación #{programacion.id}: {e}")
                logger.error(traceback.format_exc())
                db.session.rollback()
    
    def _execute_scheduled_backup(self, programacion):
        """Ejecutar un respaldo programado"""
        try:
            # Importar funciones necesarias desde routes
            from app.routes import calcular_checksum, detectar_usb_json
            
            # Configuración
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"respaldo_programado_{programacion.tipo_respaldo}_{timestamp}.sql.gz"
            
            # Determinar almacenamiento
            if programacion.almacenamiento == 'usb':
                usb_info = detectar_usb_json()
                if usb_info.get('conectado'):
                    # Crear carpeta en USB
                    usb_backup_folder = os.path.join(usb_info['ruta'], 'respaldos_gestion_plantas')
                    os.makedirs(usb_backup_folder, exist_ok=True)
                    filepath = os.path.join(usb_backup_folder, filename)
                    almacenamiento = 'usb'
                else:
                    logger.warning("USB no disponible, guardando localmente")
                    filepath = os.path.join('backups', filename)
                    almacenamiento = 'local'
            else:
                filepath = os.path.join('backups', filename)
                almacenamiento = 'local'
            
            # Obtener configuración de la base de datos
            db_config = self.app.config
            db_host = db_config.get('MYSQL_HOST', 'localhost')
            db_user = db_config.get('MYSQL_USER', 'root')
            db_password = db_config.get('MYSQL_PASSWORD', '')
            db_name = db_config.get('MYSQL_DATABASE', 'gestion_plantas')
            
            # Ruta temporal
            temp_file = os.path.join('backups', f"temp_programado_{timestamp}.sql")
            
            # Construir comando mysqldump
            if db_password:
                cmd = ['mysqldump', '-h', db_host, '-u', db_user, f'-p{db_password}', db_name]
            else:
                cmd = ['mysqldump', '-h', db_host, '-u', db_user, db_name]
            
            # Ejecutar comando
            with open(temp_file, 'w') as f:
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                raise Exception(f'Error mysqldump: {result.stderr[:200]}')
            
            # Comprimir archivo
            with open(temp_file, 'rb') as f_in:
                with gzip.open(filepath, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Limpiar archivo temporal
            if os.path.exists(temp_file):
                os.remove(temp_file)
            
            # Calcular tamaño y checksum
            tamaño_mb = os.path.getsize(filepath) / (1024 * 1024)
            checksum = calcular_checksum(filepath)
            
            # Crear registro en base de datos
            nuevo_respaldo = Respaldo(
                tipo_respaldo=f"programado_{programacion.tipo_respaldo}",
                ruta_archivo=filepath,
                tamaño_mb=round(tamaño_mb, 2),
                realizado_por=f"Sistema (Programado #{programacion.id})",
                almacenamiento=almacenamiento,
                checksum=checksum,
                fecha_respaldo=datetime.utcnow()
            )
            
            db.session.add(nuevo_respaldo)
            db.session.commit()
            
            logger.info(f"Respaldo programado completado: {filename} ({tamaño_mb:.2f} MB)")
            
        except Exception as e:
            logger.error(f"Error ejecutando respaldo programado: {e}")
            raise
    
    def ejecutar_ahora(self, programacion_id):
        """Ejecutar una programación inmediatamente"""
        with self.app.app_context():
            programacion = ProgramacionRespaldo.query.get(programacion_id)
            if programacion and programacion.activo:
                self._execute_scheduled_backup(programacion)
                programacion.ultima_ejecucion = datetime.utcnow()
                programacion.proxima_ejecucion = programacion.calcular_proxima_ejecucion()
                db.session.commit()
                return True
        return False

# Instancia global del planificador
backup_scheduler = BackupScheduler()