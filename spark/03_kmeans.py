# 03_kmeans.py - KMEANS DISTRIBUIDO CON SPARK + MONGODB

import sys
import os

# --- 1. CORRECCIÓN DE RUTAS DE ALTA PRIORIDAD ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# --- 2. SOLUCIÓN COMPATIBILIDAD PYTHON 3.12 ---
try:
    import setuptools
except ImportError:
    print("Falta la librería 'setuptools'. Ejecuta: pip install setuptools")

# --- 3. IMPORTACIONES ---
from config.mongo_spark_conexion_sinnulos import get_spark_session
from pyspark.ml.clustering import KMeans
from pyspark.ml.evaluation import ClusteringEvaluator
from pyspark.sql.functions import col

def main():
    print("\n" + "="*40)
    print("=== INICIANDO KMEANS DISTRIBUIDO ===")
    print("="*40 + "\n")

    # 1.- Obtener sesión y DataFrame
    try:
        spark, df, df_vector = get_spark_session()
        
        # --- SOLUCIÓN AL ERROR DE TIMEOUT / MONGO TIMEOUT ---
        # Forzamos a Spark a guardar los datos en memoria RAM (Cache)
        # Esto evita que el Evaluador intente volver a leer de Atlas y falle la conexión
        df_vector = df_vector.cache()
        df_vector.count() # Acción para materializar el cache inmediatamente
        
    except Exception as e:
        print(f"❌ Error al conectar con MongoDB: {e}")
        return

    # Validar nombres de columnas
    if "stock" in df.columns and "cantidad" not in df.columns:
        df_vector = df_vector.withColumnRenamed("stock", "cantidad")

    total = df_vector.count()
    if total < 3:
        print("\n⚠️ No hay suficientes datos para clustering.")
        spark.stop()
        return

    print(f"✅ Total registros cargados y cacheados: {total}\n")

    # 2.- Definir modelo
    kmeans = KMeans(
        k=3,
        seed=42,
        featuresCol="features",
        predictionCol="cluster"
    )

    # 3.- Entrenamiento
    print("🔄 Entrenando modelo K-Means...")
    model = kmeans.fit(df_vector)

    # 4.- Predicción
    result = model.transform(df_vector)
    # Cacheamos el resultado de la predicción para la evaluación
    result = result.cache()

    print("\n=== MUESTRA DE RESULTADOS ===")
    cols_a_mostrar = [c for c in ["stock", "cantidad", "precio", "ingreso", "cluster"] if c in result.columns]
    result.select(cols_a_mostrar).show(10)

    # 5.- Evaluación (Silhouette Score)
    print("📊 Calculando métricas de precisión...")
    try:
        evaluator = ClusteringEvaluator(
            featuresCol="features",
            predictionCol="cluster",
            metricName="silhouette"
        )

        silhouette = evaluator.evaluate(result)
        
        print(f"📊 Silhouette Score: {round(silhouette, 4)}")

        if silhouette > 0.5:
            print("✨ Resultado: Excelente segmentación")
        elif silhouette > 0.2:
            print("✅ Resultado: Segmentación aceptable")
        else:
            print("⚠️ Resultado: Segmentación débil")
            
    except Exception as e:
        print(f"⚠️ No se pudo completar la evaluación Silhouette: {e}")
        print("Sugerencia: Revisa que tu IP esté permitida en MongoDB Atlas.")

    # 6.- Centroides
    print("\n=== POSICIÓN DE CENTROIDES (Vectores) ===")
    centers = model.clusterCenters()
    for i, center in enumerate(centers):
        print(f"Cluster {i} (Centroide): {center}")

    # 7.- Distribución de registros
    print("\n=== DISTRIBUCIÓN DE PLANTAS POR CLUSTER ===")
    result.groupBy("cluster").count().orderBy("cluster").show()

    # Limpiar memoria
    df_vector.unpersist()
    result.unpersist()
    spark.stop()
    print("\n✅ Proceso finalizado exitosamente.")

if __name__ == "__main__":
    main()