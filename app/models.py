# app/models.py
from bson.objectid import ObjectId
from app.database import get_db

class UsuarioModel:
    @staticmethod
    def _get_collection():
        return get_db().users

    @staticmethod
    def get_all():
        return list(UsuarioModel._get_collection().find())

    @staticmethod
    def get_by_id(usuario_id):
        return UsuarioModel._get_collection().find_one({"_id": ObjectId(usuario_id)})

    @staticmethod
    def get_by_email(email):
        return UsuarioModel._get_collection().find_one({"correo": email})

    @staticmethod
    def create(data):
        result = UsuarioModel._get_collection().insert_one(data)
        return result.inserted_id


class PlantaModel:
    @staticmethod
    def _get_collection():
        return get_db().plants

    @staticmethod
    def get_all():
        return list(PlantaModel._get_collection().find())

    @staticmethod
    def get_by_id(planta_id):
        return PlantaModel._get_collection().find_one({"_id": ObjectId(planta_id)})
        
    @staticmethod
    def get_by_usuario(usuario_id):
        return list(PlantaModel._get_collection().find({"usuario_id": ObjectId(usuario_id)}))
    
    @staticmethod
    def create(data):
        result = PlantaModel._get_collection().insert_one(data)
        return result.inserted_id

    @staticmethod
    def update(planta_id, update_data):
        return PlantaModel._get_collection().update_one(
            {"_id": ObjectId(planta_id)},
            {"$set": update_data}
        )

    @staticmethod
    def delete(planta_id):
        return PlantaModel._get_collection().delete_one({"_id": ObjectId(planta_id)})

    # === MÉTODOS PARA LA TIENDA ONLINE ===
    @staticmethod
    def get_disponibles():
        return list(PlantaModel._get_collection().find({
            "disponible_venta": True, 
            "estado": "activa", 
            "stock": {"$gt": 0}
        }))

    @staticmethod
    def get_categorias_disponibles():
        # Obtiene una lista única de categorías de las plantas en venta
        return PlantaModel._get_collection().distinct("categoria", {"disponible_venta": True})

    @staticmethod
    def get_by_categoria(categoria, exclude_id=None, limit=4):
        query = {
            "categoria": categoria, 
            "disponible_venta": True, 
            "estado": "activa", 
            "stock": {"$gt": 0}
        }
        if exclude_id:
            query["_id"] = {"$ne": ObjectId(exclude_id)}
            
        return list(PlantaModel._get_collection().find(query).limit(limit))

    @staticmethod
    def buscar_avanzada(query_text, precio_min, precio_max, categoria):
        # Construcción dinámica de la consulta para el buscador de la tienda
        filtros = {
            "disponible_venta": True, 
            "estado": "activa", 
            "stock": {"$gt": 0}
        }
        
        if query_text:
            # $regex permite buscar coincidencias parciales de texto (ignorando mayúsculas/minúsculas)
            filtros["$or"] = [
                {"nombre": {"$regex": query_text, "$options": "i"}},
                {"especie": {"$regex": query_text, "$options": "i"}},
                {"descripcion": {"$regex": query_text, "$options": "i"}}
            ]
            
        if precio_min is not None:
            filtros.setdefault("precio", {})["$gte"] = float(precio_min)
            
        if precio_max is not None:
            filtros.setdefault("precio", {})["$lte"] = float(precio_max)
            
        if categoria:
            filtros["categoria"] = categoria
            
        return list(PlantaModel._get_collection().find(filtros))


class PedidoModel:
    @staticmethod
    def _get_collection():
        return get_db().orders

    @staticmethod
    def get_by_usuario(usuario_id):
        return list(PedidoModel._get_collection().find({"id_cliente": ObjectId(usuario_id)}))

    @staticmethod
    def get_by_id(pedido_id):
        return PedidoModel._get_collection().find_one({"_id": ObjectId(pedido_id)})
        
    @staticmethod
    def create(data):
        result = PedidoModel._get_collection().insert_one(data)
        return result.inserted_id


# === NUEVOS MODELOS FALTANTES ===

class RegistroRiegoModel:
    @staticmethod
    def _get_collection():
        return get_db().watering_logs

    @staticmethod
    def create(data):
        result = RegistroRiegoModel._get_collection().insert_one(data)
        return result.inserted_id

    @staticmethod
    def get_by_planta(planta_id, limit=5):
        # Ordenamos por fecha_riego descendente (-1) y limitamos resultados
        return list(RegistroRiegoModel._get_collection().find(
            {"id_planta": ObjectId(planta_id)}
        ).sort("fecha_riego", -1).limit(limit))


class HistorialModel:
    @staticmethod
    def _get_collection():
        return get_db().access_logs

    @staticmethod
    def create(data):
        result = HistorialModel._get_collection().insert_one(data)
        return result.inserted_id