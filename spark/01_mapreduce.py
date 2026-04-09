import sys
import os

# Esto permite que Python encuentre la carpeta 'config' desde la terminal
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config.mongo_spark_conexion_sinnulos import get_spark_session
from pyspark.sql.functions import sum

# Obtenemos la sesión y el DataFrame
spark, df, _ = get_spark_session()

print("=========================================")
print("=== EJECUTANDO ALGORITMO MAPREDUCE ===")
print("=========================================")

# Agrupa por producto y suma el ingreso
df.groupBy("producto") \
  .agg(sum("ingreso").alias("total_ingreso")) \
  .orderBy("total_ingreso", ascending=False) \
  .show()

# Apagar Spark correctamente
spark.stop()