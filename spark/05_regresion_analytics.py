# LABORATORIO DE MACHINE LEARNING CON SPARK - COMPARACIÓN DE MODELOS DE REGRESIÓN
import streamlit as st
import sys
import os
import matplotlib.pyplot as plt
import pandas as pd

# --- 1. CONFIGURACIÓN DE RUTAS (Solución al ModuleNotFoundError) ---
# Obtenemos la ruta raíz para que encuentre la carpeta 'config'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- 2. COMPATIBILIDAD PYTHON 3.12 ---
try:
    import setuptools
except ImportError:
    st.error("Falta la librería 'setuptools'. Ejecuta: pip install setuptools")

# --- 3. IMPORTACIONES DE SPARK ---
from config.mongo_spark_conexion_sinnulos import get_spark_session
from pyspark.ml.feature import VectorAssembler, PolynomialExpansion
from pyspark.ml.regression import LinearRegression
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.tuning import CrossValidator, ParamGridBuilder

# Título para la interfaz de Streamlit
st.title("Análisis de Regresión de Plantas")

# 1 CREAR SESIÓN SPARK Y CARGAR DATOS
# Cargamos la sesión configurada para tu clúster de MongoDB Atlas
spark, df, _ = get_spark_session()

st.write("### Dataset cargado desde MongoDB Atlas")

# LIMPIEZA PREVENTIVA: Borramos columnas de características si existen por ejecuciones previas
def limpiar_columnas(df_input):
    for col_name in ["features", "poly_features", "prediction"]:
        if col_name in df_input.columns:
            df_input = df_input.drop(col_name)
    return df_input

# Aseguramos que solo trabajamos con registros que tengan ingreso
df = df.filter(df.ingreso > 0).cache() 
st.dataframe(df.limit(5).toPandas())

# 2 DIVISIÓN DEL DATASET
train, test = df.randomSplit([0.8, 0.2], seed=42)

# 3 MÉTRICA DE EVALUACIÓN
evaluator = RegressionEvaluator(
    labelCol="ingreso",
    predictionCol="prediction",
    metricName="r2"
)

# 4 FUNCIÓN PARA CREAR GRÁFICAS
def graficar(predictions, titulo):
    pdf = predictions.select("stock", "ingreso", "prediction").toPandas()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.scatter(pdf["stock"], pdf["ingreso"], label="Real", alpha=0.6, color='blue')
    ax.scatter(pdf["stock"], pdf["prediction"], label="Predicción", marker='x', color='red')
    ax.set_title(titulo)
    ax.set_xlabel("Stock (Unidades)")
    ax.set_ylabel("Ingreso ($)")
    ax.legend()
    ax.grid(True, linestyle='--', alpha=0.7)
    st.pyplot(fig)

# --- MODELO 1: REGRESIÓN LINEAL SIMPLE ---
st.subheader("Modelo 1: Regresión Lineal Simple")
train = limpiar_columnas(train)
test = limpiar_columnas(test)

assembler_simple = VectorAssembler(inputCols=["stock"], outputCol="features")
train_simple = assembler_simple.transform(train)
test_simple = assembler_simple.transform(test)

lr_simple = LinearRegression(featuresCol="features", labelCol="ingreso")
model_simple = lr_simple.fit(train_simple)
pred_simple = model_simple.transform(test_simple)
r2_simple = evaluator.evaluate(pred_simple)

st.info(f"R2 Simple: **{r2_simple:.4f}**")
graficar(pred_simple, "Regresión Lineal Simple (Stock vs Ingreso)")

# --- MODELO 2: REGRESIÓN LINEAL MÚLTIPLE ---
st.subheader("Modelo 2: Regresión Lineal Múltiple")
# Limpiamos antes de re-ensamblar con más columnas
train_m = limpiar_columnas(train)
test_m = limpiar_columnas(test)

assembler_multiple = VectorAssembler(inputCols=["stock", "precio"], outputCol="features")
train_multiple = assembler_multiple.transform(train_m)
test_multiple = assembler_multiple.transform(test_m)

lr_multiple = LinearRegression(featuresCol="features", labelCol="ingreso")
model_multiple = lr_multiple.fit(train_multiple)
pred_multiple = model_multiple.transform(test_multiple)
r2_multiple = evaluator.evaluate(pred_multiple)

st.info(f"R2 Múltiple: **{r2_multiple:.4f}**")
graficar(pred_multiple, "Regresión Lineal Múltiple (Stock + Precio)")

# --- MODELOS 3 Y 4: RIDGE Y LASSO ---
model_ridge = LinearRegression(featuresCol="features", labelCol="ingreso", regParam=0.5, elasticNetParam=0).fit(train_multiple)
r2_ridge = evaluator.evaluate(model_ridge.transform(test_multiple))

model_lasso = LinearRegression(featuresCol="features", labelCol="ingreso", regParam=0.5, elasticNetParam=1).fit(train_multiple)
r2_lasso = evaluator.evaluate(model_lasso.transform(test_multiple))

# --- MODELO 5: REGRESIÓN POLINÓMICA ---
st.subheader("Modelo 5: Regresión Polinómica")
poly = PolynomialExpansion(inputCol="features", outputCol="poly_features", degree=2)
train_poly = poly.transform(train_multiple)
test_poly = poly.transform(test_multiple)

lr_poly = LinearRegression(featuresCol="poly_features", labelCol="ingreso")
model_poly = lr_poly.fit(train_poly)
pred_poly = model_poly.transform(test_poly)
r2_poly = evaluator.evaluate(pred_poly)
st.info(f"R2 Polinómica: **{r2_poly:.4f}**")
graficar(pred_poly, "Regresión Polinómica (Grado 2)")

# --- MODELO 6: CROSS VALIDATION ---
st.subheader("Modelo 6: Cross Validation (Optimizado)")
lr_cv = LinearRegression(featuresCol="features", labelCol="ingreso")
paramGrid = ParamGridBuilder().addGrid(lr_cv.regParam, [0.1, 1.0]).build()
cv = CrossValidator(estimator=lr_cv, estimatorParamMaps=paramGrid, evaluator=evaluator, numFolds=2)
model_cv = cv.fit(train_multiple)
r2_cv = evaluator.evaluate(model_cv.transform(test_multiple))

# --- COMPARACIÓN FINAL ---
st.divider()
st.header("Resumen de Resultados (R²)")
resultados = {
    "Lineal Simple": r2_simple,
    "Lineal Multiple": r2_multiple,
    "Ridge": r2_ridge,
    "Lasso": r2_lasso,
    "Polinomial": r2_poly,
    "Cross Validation": r2_cv
}

res_df = pd.DataFrame(list(resultados.items()), columns=["Modelo", "R2 Score"])
st.table(res_df)

mejor = max(resultados, key=resultados.get)
st.success(f"### EL MEJOR MODELO ES: {mejor.upper()}")

# Limpiar
df.unpersist()