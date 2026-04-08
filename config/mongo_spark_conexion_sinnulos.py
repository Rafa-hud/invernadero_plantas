from pyspark.sql import SparkSession
from pyspark.sql.functions import col

def get_spark_session():
    # En Java 11 ya no necesitamos tantos "parches" de seguridad
    spark = SparkSession.builder \
        .appName("InvernaderoSpark") \
        .config("spark.mongodb.input.uri", "mongodb+srv://admin:Emmanuel123@cluster0.cerffq3.mongodb.net/invernadero_db.plants") \
        .config("spark.mongodb.output.uri", "mongodb+srv://admin:Emmanuel123@cluster0.cerffq3.mongodb.net/invernadero_db.plants") \
        .config("spark.jars.packages", "org.mongodb.spark:mongo-spark-connector_2.12:3.0.1") \
        .getOrCreate()

    # Carga de datos
    df = spark.read.format("mongo").load()

    # Mapeo de columnas: nombre (de Atlas) -> producto
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