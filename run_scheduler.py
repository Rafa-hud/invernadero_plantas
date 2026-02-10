#!/usr/bin/env python3
# run_scheduler.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.scheduler import backup_scheduler
import logging

logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        backup_scheduler.start(app)
        print("Planificador iniciado. Presiona Ctrl+C para detener.")
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            backup_scheduler.stop()
            print("Planificador detenido.")