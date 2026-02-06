#!/usr/bin/env python3
"""
Script de backup automático para Sistema de Gestión de Plantas
"""

import os
import sys
import argparse
from pathlib import Path

# Agregar ruta del proyecto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.utils import backup_manager

def main():
    parser = argparse.ArgumentParser(description='Script de backup del sistema')
    parser.add_argument('--tipo', choices=['completo', 'diferencial', 'minima_modificacion'],
                       default='completo', help='Tipo de respaldo')
    parser.add_argument('--usuario', default='Sistema (script)',
                       help='Nombre del usuario que realiza el respaldo')
    parser.add_argument('--config', default='development',
                       choices=['development', 'production'],
                       help='Configuración a usar')
    
    args = parser.parse_args()
    
    # Crear aplicación
    app = create_app(config_name=args.config)
    
    # Inicializar backup manager
    backup_manager.init_app(app)
    
    with app.app_context():
        try:
            backup_file = backup_manager.create_backup(args.tipo, args.usuario)
            print(f"✅ Backup creado exitosamente: {backup_file}")
            return 0
        except Exception as e:
            print(f"❌ Error al crear backup: {str(e)}", file=sys.stderr)
            return 1

if __name__ == '__main__':
    sys.exit(main())