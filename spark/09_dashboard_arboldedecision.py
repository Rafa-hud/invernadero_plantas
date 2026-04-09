import sys
import os
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# --- 1. CORRECCIÓN DE RUTAS Y ENTORNO ---
# Obtenemos la ruta absoluta de la carpeta raíz 'Invernadero_plantas-'
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))

# Insertamos la raíz al inicio para que encuentre el paquete 'app' y sus submódulos
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# --- 2. CORRECCIÓN PARA PYTHON 3.12 ---
try:
    import setuptools
except ImportError:
    st.error("Falta la librería 'setuptools'. Ejecuta: pip install setuptools")
    st.stop()

# Importaciones de Spark
from pyspark.sql.functions import col, when
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.classification import DecisionTreeClassifier
from pyspark.ml.evaluation import MulticlassClassificationEvaluator

# --- 3. IMPORTACIÓN DINÁMICA (CORREGIDA PARA APP/CONFIG) ---
try:
    # Ahora la ruta incluye 'app' para coincidir con tu nueva estructura
    from app.config.mongo_spark_conexion_sinnulos import get_spark_session
except ImportError as e:
    st.error(f"❌ Error de configuración: {e}")
    st.info(f"Buscando en: {root_dir}/app/config")
    st.stop()

# CONFIGURACIÓN DEL DASHBOARD
st.set_page_config(page_title="Dashboard Árbol de Decisión", layout="wide", page_icon="🌲")
st.title("🌲 Clasificación de Ventas: IA Lógica")
st.markdown("Árboles de decisión para calificar la rentabilidad de las especies del invernadero.")

# --- 4. CARGAR DATOS (Cacheada para estabilidad) ---
@st.cache_resource
def iniciar_spark_clasificacion():
    # get_spark_session devuelve: spark, df_full, df_vector
    spark, df, _ = get_spark_session()
    
    # Limpiamos caché previa para evitar errores de conexión socket
    spark.catalog.clearCache()
    
    # Aseguramos que la columna ingreso existe para el entrenamiento
    if "stock" in df.columns and "ingreso" not in df.columns:
        df = df.withColumn("ingreso", col("stock") * col("precio"))
    
    # Creamos la etiqueta: 1 para ventas altas, 0 para bajas
    df = df.withColumn("label", when(col("ingreso") > 50000, 1).otherwise(0))
    return spark, df

try:
    spark, df_spark = iniciar_spark_clasificacion()
except Exception as e:
    st.error(f"Error de conexión con MongoDB Atlas: {e}")
    st.stop()

# --- 5. FILTROS Y PREPARACIÓN DE PANDAS ---
st.sidebar.header("🛠️ Configuración IA")
df_pandas = df_spark.toPandas()
productos = sorted(df_pandas["producto"].unique())
producto_filtro = st.sidebar.selectbox("Filtrar por Producto", ["Todos"] + list(productos))

if producto_filtro != "Todos":
    df_pandas = df_pandas[df_pandas["producto"] == producto_filtro]

# --- 6. VISUALIZACIÓN EXPLORATORIA ---
st.subheader("📋 Vista Previa de Datos")
st.dataframe(df_pandas.head(10), use_container_width=True)

col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Ingresos por Producto")
    ventas_prod = df_pandas.groupby("producto")["ingreso"].sum().sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(8, 4))
    # Aplicamos un estilo oscuro para que combine con tu web
    plt.style.use('dark_background')
    ventas_prod.plot(kind="bar", ax=ax, color='#28a745')
    ax.set_ylabel("Ingresos ($)")
    st.pyplot(fig)

with col2:
    st.subheader("⚖️ Distribución de Rentabilidad")
    clases = df_pandas["label"].value_counts().rename({1: "Alta", 0: "Baja"})
    fig2, ax2 = plt.subplots(figsize=(8, 4))
    clases.plot(kind="pie", autopct='%1.1f%%', ax=ax2, colors=['#dc3545','#28a745'])
    st.pyplot(fig2)

# --- 7. ENTRENAMIENTO DEL MODELO ---
st.divider()
st.subheader("🤖 Entrenamiento del Clasificador")

if 'modelo_entrenado' not in st.session_state:
    st.session_state.modelo_entrenado = None

if st.button("Entrenar Árbol de Decisión"):
    with st.spinner("Spark está procesando el árbol lógico..."):
        # Convertimos de nuevo a Spark para el entrenamiento ML
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

        # Configuramos el árbol
        dt = DecisionTreeClassifier(featuresCol="features", labelCol="label", maxDepth=5)
        model = dt.fit(train_data)
        st.session_state.modelo_entrenado = model 
        
        predictions = model.transform(test_data)
        evaluator = MulticlassClassificationEvaluator(labelCol="label", metricName="accuracy")
        accuracy = evaluator.evaluate(predictions)

        st.success(f"Modelo optimizado. Precisión del sistema: **{accuracy:.2%}**")
        with st.expander("Ver estructura lógica del árbol (Debug String)"):
            st.text(model.toDebugString)

# --- 8. PREDICCIÓN INTERACTIVA ---
st.divider()
st.subheader("🔮 Simulador de Ventas")

c1, c2 = st.columns(2)
with c1:
    val_stock = st.number_input("Cantidad/Stock a evaluar", min_value=1, value=5)
with c2:
    val_precio = st.number_input("Precio unitario de venta ($)", min_value=1.0, value=15000.0)

val_ingreso = val_stock * val_precio
st.info(f"Ingreso estimado: **${val_ingreso:,.2f}**")

if st.button("Ejecutar Clasificación"):
    if st.session_state.modelo_entrenado is not None:
        assembler_pred = VectorAssembler(inputCols=["stock", "precio", "ingreso"], outputCol="features")
        pred_df = spark.createDataFrame([(val_stock, val_precio, val_ingreso)], ["stock", "precio", "ingreso"])
        pred_df_vect = assembler_pred.transform(pred_df)
        
        res = st.session_state.modelo_entrenado.transform(pred_df_vect)
        clase = res.select("prediction").collect()[0][0]
        
        if clase == 1.0:
            st.success("Predicción: **RECURSO ALTAMENTE RENTABLE** 💰")
        else:
            st.warning("Predicción: **RECURSO DE BAJO IMPACTO** 📉")
    else:
        st.error("Por favor, entrena el modelo antes de clasificar.")

# Botón lateral para liberar recursos
with st.sidebar:
    st.divider()
    if st.button("Detener Clúster"):
        spark.stop()
        st.success("Sesión de Spark cerrada.")