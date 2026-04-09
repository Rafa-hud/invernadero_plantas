# 1. Importar librerías

from pyspark.sql.functions import when, col
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.classification import DecisionTreeClassifier
from pyspark.ml.evaluation import MulticlassClassificationEvaluator

# Importamos tu función que carga datos desde Mongo
from app.config.mongo_spark_conexion_sinnulos import get_spark_session


# 2. Cargar datos

spark, df, df_vector = get_spark_session()

print("\nDataset original")
df.show()


# 3. Crear etiqueta (label)
"""
Queremos que el modelo prediga si una venta es ALTA o BAJA

Regla:
si ingreso > 50000 → 1
si ingreso <= 50000 → 0
"""

df = df.withColumn(
    "label",
    when(col("ingreso") > 50000, 1).otherwise(0)
)

print("\nDataset con etiqueta")
df.select("producto", "cantidad", "precio", "ingreso", "label").show()


# 4. Limpieza de datos

df = df.dropna(subset=["cantidad", "precio", "ingreso"])

# 5. Crear features

assembler = VectorAssembler(
    inputCols=["cantidad", "precio", "ingreso"],
    outputCol="features",
    handleInvalid="skip"  # evita error con null
)

df_ml = assembler.transform(df)

# 6. Seleccionar dataset final

dataset = df_ml.select("features", "label")

print("\nDataset listo para Machine Learning")
dataset.show()

# 7. Dividir datos entrenamiento / prueba

train_data, test_data = dataset.randomSplit([0.8, 0.2], seed=42)

print("Datos de entrenamiento:", train_data.count())
print("Datos de prueba:", test_data.count())


# 8. Crear modelo Decision Tree

dt = DecisionTreeClassifier(
    featuresCol="features",
    labelCol="label",
    maxDepth=3
)


# 9. Entrenar modelo

model = dt.fit(train_data)

print("\nModelo entrenado")


# 10. Mostrar árbol aprendido

print("\nEstructura del árbol:\n")

print(model.toDebugString)


# 11. Realizar predicciones

predictions = model.transform(test_data)

print("\nPredicciones")
predictions.select("features", "label", "prediction").show()


# 12. Evaluar modelo

evaluator = MulticlassClassificationEvaluator(
    labelCol="label",
    predictionCol="prediction",
    metricName="accuracy"
)

accuracy = evaluator.evaluate(predictions)

print("\nAccuracy del modelo:", accuracy)


# 13. Finalizar sesión

spark.stop()
