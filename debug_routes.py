# debug_routes.py
from flask import Blueprint, jsonify, current_app
import traceback

debug_bp = Blueprint('debug', __name__)

@debug_bp.route('/test-usb-route')
def test_usb_route():
    """Ruta de prueba para USB"""
    try:
        return jsonify({
            'success': True,
            'message': 'Ruta de prueba funcionando',
            'routes': {
                'copiar_a_usb': '/backup/copiar-a-usb [POST]',
                'detectar_usb': '/backup/detectar-usb [GET]',
                'listar_respaldos': '/backup/ [GET]'
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@debug_bp.route('/check-backup-routes')
def check_backup_routes():
    """Verificar todas las rutas de backup"""
    try:
        routes = []
        for rule in current_app.url_map.iter_rules():
            if 'backup' in rule.endpoint:
                routes.append({
                    'endpoint': rule.endpoint,
                    'rule': str(rule),
                    'methods': list(rule.methods)
                })
        
        return jsonify({
            'success': True,
            'total_routes': len(routes),
            'routes': routes
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500