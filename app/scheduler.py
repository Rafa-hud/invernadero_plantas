# app/scheduler.py
import threading
import time
from datetime import datetime, timedelta
import logging
import traceback
import os
import gzip
from bson import ObjectId, json_util
from app.database import get_db

logger = logging.getLogger(__name__)

def calcular_proxima_ejecucion(programacion):
    """
    Calcula la próxima fecha de ejecución basada en la configuración.
    Reemplaza al antiguo método del modelo relacional.
    """
    ahora = datetime.utcnow()
    
    # Manejar el formato de la hora (puede venir como string o objeto time)
    hora_dato = programacion.get('hora_ejecucion', '02:00')
    if hasattr(hora_dato, 'strftime'):
        hora_str = hora_dato.strftime('%H:%M')
    else:
        hora_str = str(hora_dato)
        
    hora, minuto = map(int, hora_str.split(':'))
    
    # Base: hoy a la hora configurada
    proxima = ahora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    
    # Si la hora ya pasó hoy, base para el cálculo es mañana
    if proxima <= ahora:
        proxima += timedelta(days=1)
        
    frecuencia = programacion.get('frecuencia', 'diario')
    
    if frecuencia == 'semanal':
        # dias_semana suele ser "0,2,4" (lunes, miércoles, viernes)
        dias_str = programacion.get('dias_semana', '0')
        if dias_str:
            dias_permitidos = [int(d) for d in dias_str.split(',')]
            while proxima.weekday() not in dias_permitidos:
                proxima += timedelta(days=1)
                
    elif frecuencia == 'mensual':
        dia_objetivo = int(programacion.get('dia_mes', 1))
        # Avanzar días hasta coincidir con el día del mes
        while proxima.day != dia_objetivo:
            proxima += timedelta(days=1)
            
    return proxima


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
            from app import create_app
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
        """Verificar y ejecutar respaldos programados en MongoDB"""
        ahora = datetime.utcnow()
        db = get_db()
        
        # Obtener programaciones activas (Equivalente a .filter_by(activo=True))
        programaciones = list(db.schedules.find({'activo': True}))
        
        for programacion in programaciones:
            try:
                prog_id = programacion['_id']
                
                # Verificar si no tiene fecha calculada
                if not programacion.get('proxima_ejecucion'):
                    nueva_fecha = calcular_proxima_ejecucion(programacion)
                    db.schedules.update_one({'_id': prog_id}, {'$set': {'proxima_ejecucion': nueva_fecha}})
                    programacion['proxima_ejecucion'] = nueva_fecha
                
                # Ejecutar si ya pasó la hora
                if programacion['proxima_ejecucion'] <= ahora:
                    logger.info(f"Ejecutando respaldo programado #{prog_id} - {programacion.get('tipo_respaldo')}")
                    
                    self._execute_scheduled_backup(programacion)
                    
                    # Actualizar fechas para el próximo ciclo
                    prox = calcular_proxima_ejecucion(programacion)
                    db.schedules.update_one(
                        {'_id': prog_id}, 
                        {'$set': {'ultima_ejecucion': ahora, 'proxima_ejecucion': prox}}
                    )
                    
                    logger.info(f"Respaldo programado completado. Próxima ejecución: {prox}")
                    
            except Exception as e:
                logger.error(f"Error ejecutando programación #{programacion.get('_id')}: {e}")
                logger.error(traceback.format_exc())
    
    def _execute_scheduled_backup(self, programacion):
        """Ejecutar un respaldo extrayendo datos con PyMongo"""
        try:
            # Importaciones locales para evitar dependencias circulares
            from app.routes import calcular_checksum, detectar_usb_json
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            tipo = programacion.get('tipo_respaldo', 'completo')
            filename = f"respaldo_programado_{tipo}_{timestamp}.json.gz"
            
            # Determinar almacenamiento
            if programacion.get('almacenamiento') == 'usb':
                usb_info = detectar_usb_json()
                if usb_info.get('conectado'):
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
            
            db = get_db()
            
            # 1. EXTRACCIÓN CON PYMONGO
            data_to_backup = {}
            for coll_name in db.list_collection_names():
                data_to_backup[coll_name] = list(db[coll_name].find())
            
            # 2. CONVERSIÓN Y COMPRESIÓN
            json_data = json_util.dumps(data_to_backup)
            
            with gzip.open(filepath, 'wt', encoding='utf-8') as f_out:
                f_out.write(json_data)
            
            # 3. REGISTRO EN BASE DE DATOS
            tamaño_mb = os.path.getsize(filepath) / (1024 * 1024)
            checksum = calcular_checksum(filepath)
            
            nuevo_respaldo = {
                'tipo_respaldo': f"programado_{tipo}",
                'ruta_archivo': filepath,
                'tamaño_mb': round(tamaño_mb, 2),
                'realizado_por': f"Sistema (Programado #{programacion['_id']})",
                'almacenamiento': almacenamiento,
                'checksum': checksum,
                'fecha_respaldo': datetime.utcnow()
            }
            
            db.backups.insert_one(nuevo_respaldo)
            logger.info(f"Respaldo programado completado: {filename} ({tamaño_mb:.2f} MB)")
            
        except Exception as e:
            logger.error(f"Error ejecutando respaldo programado: {e}")
            raise
    
    def ejecutar_ahora(self, programacion_id):
        """Ejecutar una programación inmediatamente"""
        with self.app.app_context():
            db = get_db()
            programacion = db.schedules.find_one({'_id': ObjectId(programacion_id)})
            
            if programacion and programacion.get('activo'):
                self._execute_scheduled_backup(programacion)
                
                prox = calcular_proxima_ejecucion(programacion)
                db.schedules.update_one(
                    {'_id': ObjectId(programacion_id)},
                    {'$set': {'ultima_ejecucion': datetime.utcnow(), 'proxima_ejecucion': prox}}
                )
                return True
        return False

# Instancia global del planificador
backup_scheduler = BackupScheduler()