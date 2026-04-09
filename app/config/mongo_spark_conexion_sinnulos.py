from pyspark.sql import SparkSession
from pyspark.sql.functions import col
import os

# ========== BLOQUE DE CONFIGURACIÓN PARA FLASK ==========
# Esto es lo que le faltaba a tu archivo para que run.py no diera error
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave-secreta-invernadero'
    APP_NAME = "Intelligence Plant"
    # Añade aquí otras variables que use tu app (MAIL_SERVER, etc.)

class DevelopmentConfig(Config):
    DEBUG = True

# Este es el diccionario exacto que busca tu app/__init__.py
config = {
    'development': DevelopmentConfig,
    'default': DevelopmentConfig
}

# ========== BLOQUE DE CONEXIÓN SPARK ==========
def get_spark_session():
    # Tu lógica actual de Spark se mantiene intacta
    spark = SparkSession.builder \
        .appName("InvernaderoSpark") \
        .config("spark.mongodb.input.uri", "mongodb+srv://admin:Emmanuel123@cluster0.cerffq3.mongodb.net/invernadero_db.plants") \
        .config("spark.mongodb.output.uri", "mongodb+srv://admin:Emmanuel123@cluster0.cerffq3.mongodb.net/invernadero_db.plants") \
        .config("spark.jars.packages", "org.mongodb.spark:mongo-spark-connector_2.12:3.0.1") \
        .getOrCreate()

    # Carga de datos
    df = spark.read.format("mongo").load()

    # Mapeo de columnas
    df_clean = df.select(
        col("nombre").alias("producto"),
        col("precio").cast("double"),
        col("stock").cast("int")
    ).na.fill({"precio": 0.0, "stock": 0, "producto": "Desconocido"})

    # Cálculo de ingreso
    df_with_income = df_clean.withColumn("ingreso", col("precio") * col("stock"))

    # Vectorización para KMeans
    from pyspark.ml.feature import VectorAssembler
    df_train = df_with_income.filter(col("ingreso") > 0)
    
    assembler = VectorAssembler(
        inputCols=["precio", "stock", "ingreso"], 
        outputCol="features"
    )
    
    df_vector = assembler.transform(df_train)

    return spark, df_with_income, df_vector