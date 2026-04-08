import sys
import os
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# --- CORRECCIÓN PARA PYTHON 3.12 ---
# Spark requiere distutils/setuptools. Esto debe ir antes de las importaciones de pyspark.
try:
    import setuptools
except ImportError:
    st.error("Falta la librería 'setuptools'. Ejecuta en tu terminal: pip install setuptools")
    st.stop()

from pyspark.sql.functions import col, when
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.classification import DecisionTreeClassifier
from pyspark.ml.evaluation import MulticlassClassificationEvaluator

# 1. CONFIGURACIÓN DE RUTAS Y ENTORNO
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importación de la conexión segura a MongoDB
try:
    from config.mongo_spark_conexion_sinnulos import get_spark_session
except ImportError:
    st.error("Error de configuración: No se encontró el módulo 'config'. Asegúrate de que la carpeta tenga el archivo '__init__.py'")
    st.stop()

# CONFIGURACIÓN DEL DASHBOARD
st.set_page_config(page_title="Dashboard Árbol de Decisión", layout="wide")
st.title("🌲 Clasificación de Ventas: Árbol de Decisión")

# 2. CARGAR DATOS (Uso de cache_resource para mantener la sesión de Spark viva)
@st.cache_resource
def iniciar_spark_clasificacion():
    spark, df, _ = get_spark_session()
    
    # Limpiamos caché previa de Spark para evitar MongoSocketOpenException
    spark.catalog.clearCache()
    
    if "stock" in df.columns and "ingreso" not in df.columns:
        df = df.withColumn("ingreso", col("stock") * col("precio"))
    
    df = df.withColumn("label", when(col("ingreso") > 50000, 1).otherwise(0))
    return spark, df

try:
    spark, df_spark = iniciar_spark_clasificacion()
except Exception as e:
    st.error(f"Error de conexión con MongoDB: {e}")
    st.info("Asegúrate de tener activo tu venv y usar Java 11.")
    st.stop()

# 3. FILTROS Y PREPARACIÓN DE PANDAS
st.sidebar.header("🛠️ Configuración")
df_pandas = df_spark.toPandas()
productos = sorted(df_pandas["producto"].unique())
producto_filtro = st.sidebar.selectbox("Filtrar por Producto", ["Todos"] + list(productos))

if producto_filtro != "Todos":
    df_pandas = df_pandas[df_pandas["producto"] == producto_filtro]

# 4. VISUALIZACIÓN EXPLORATORIA
st.subheader("📋 Vista Previa de Datos")
st.dataframe(df_pandas.head(10))

col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Ingresos por Producto")
    ventas_prod = df_pandas.groupby("producto")["ingreso"].sum().sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(8, 4))
    ventas_prod.plot(kind="bar", ax=ax, color='skyblue')
    ax.set_ylabel("Ingresos ($)")
    st.pyplot(fig)

with col2:
    st.subheader("⚖️ Distribución de Clases")
    clases = df_pandas["label"].value_counts().rename({1: "Alta", 0: "Baja"})
    fig2, ax2 = plt.subplots(figsize=(8, 4))
    clases.plot(kind="pie", autopct='%1.1f%%', ax=ax2, colors=['#ff9999','#66b3ff'])
    st.pyplot(fig2)

# 5. ENTRENAMIENTO DEL MODELO
st.divider()
st.subheader("🤖 Entrenamiento del Clasificador")

# Inicializamos el modelo en el estado de la sesión para que la predicción lo encuentre
if 'modelo_entrenado' not in st.session_state:
    st.session_state.modelo_entrenado = None

if st.button("Entrenar Árbol de Decisión"):
    with st.spinner("Entrenando..."):
        df_ml_input = spark.createDataFrame(df_pandas)
        if "features" in df_ml_input.columns:
            df_ml_input = df_ml_input.drop("features")

        assembler = VectorAssembler(
            inputCols=["stock", "precio", "ingreso"],
            outputCol="features",
            handleInvalid="skip"
        )

        df_ml = assembler.transform(df_ml_input)
        train_data, test_data = df_ml.randomSplit([0.8, 0.2], seed=42)

        dt = DecisionTreeClassifier(featuresCol="features", labelCol="label", maxDepth=5)
        model = dt.fit(train_data)
        st.session_state.modelo_entrenado = model # Guardamos el modelo
        
        predictions = model.transform(test_data)
        evaluator = MulticlassClassificationEvaluator(labelCol="label", metricName="accuracy")
        accuracy = evaluator.evaluate(predictions)

        st.success(f"Modelo entrenado con Accuracy de: **{accuracy:.2%}**")
        with st.expander("Ver reglas del árbol"):
            st.text(model.toDebugString)

# 6. PREDICCIÓN INTERACTIVA
st.divider()
st.subheader("🔮 Predicción de Nueva Venta")

c1, c2 = st.columns(2)
with c1:
    val_stock = st.number_input("Stock/Cantidad", min_value=1, value=5)
with c2:
    val_precio = st.number_input("Precio unitario ($)", min_value=10.0, value=15000.0)

val_ingreso = val_stock * val_precio
st.info(f"Ingreso proyectado: **${val_ingreso:,.2f}**")

if st.button("Clasificar Venta"):
    if st.session_state.modelo_entrenado is not None:
        # Re-creamos assembler para la predicción
        assembler_pred = VectorAssembler(inputCols=["stock", "precio", "ingreso"], outputCol="features")
        pred_df = spark.createDataFrame([(val_stock, val_precio, val_ingreso)], ["stock", "precio", "ingreso"])
        pred_df_vect = assembler_pred.transform(pred_df)
        
        # Predicción usando el modelo guardado
        res = st.session_state.modelo_entrenado.transform(pred_df_vect)
        clase = res.select("prediction").collect()[0][0]
        
        if clase == 1.0:
            st.success("Resultado: **VENTA ALTA** 💰")
        else:
            st.warning("Resultado: **VENTA BAJA** 📉")
    else:
        st.error("Primero debes hacer clic en 'Entrenar Árbol de Decisión'.")