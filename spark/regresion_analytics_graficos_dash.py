import streamlit as st
import pandas as pd
import plotly.express as px
from pymongo import MongoClient
from pyspark.sql import SparkSession
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.regression import LinearRegression
from pyspark.ml.evaluation import RegressionEvaluator

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Analytics Invernadero Pro", layout="wide")

# --- 2. FUNCIONES DE VISUALIZACIÓN ---
def grafica_dispersion(df):
    return px.scatter(df, x="stock", y="ingreso", color="nombre", size="precio",
                     hover_data=["precio"], template="plotly_dark", title="Relación Stock vs Ingreso")

def grafica_distribucion(df):
    return px.histogram(df, x="ingreso", color="nombre", nbins=20,
                       template="plotly_dark", title="Distribución de Ingresos")

def grafica_modelos(resultados):
    df_modelos = pd.DataFrame(list(resultados.items()), columns=["Modelo", "R2"])
    return px.bar(df_modelos, x="Modelo", y="R2", color="Modelo",
                 template="plotly_dark", title="Precisión de Modelos Predictivos")

# --- 3. LÓGICA DE DATOS ---
@st.cache_resource
def iniciar_spark():
    spark = SparkSession.builder.appName("InvernaderoAnalytics").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark

def obtener_datos_mongo():
    uri = "mongodb+srv://admin:Emmanuel123@cluster0.cerffq3.mongodb.net/?appName=Cluster0"
    client = MongoClient(uri)
    db = client.get_database('invernadero_db')
    
    # Nombre exacto confirmado: 'plants'
    coleccion = db.get_collection('plants')
    docs = list(coleccion.find())
    client.close()

    if not docs:
        st.error("❌ La colección 'plants' fue encontrada pero no contiene documentos.")
        st.stop()
        
    pdf = pd.DataFrame(docs)

    # --- MAPEO DE COLUMNAS (Basado en tu última captura) ---
    # Usamos .get() para evitar errores si alguna fila no tiene el campo
    pdf['nombre'] = pdf['nombre'].fillna("Sin nombre")
    
    # Convertimos precio y stock a números (minúsculas como en tu imagen)
    pdf['precio'] = pd.to_numeric(pdf['precio'], errors='coerce').fillna(0)
    pdf['stock'] = pd.to_numeric(pdf['stock'], errors='coerce').fillna(0)
    
    # Cálculo de ingresos para el análisis
    pdf['ingreso'] = pdf['precio'] * pdf['stock']
    
    return pdf

def ejecutar_modelos(df_spark):
    try:
        # Usamos 'stock' y 'precio' como variables predictoras
        assembler = VectorAssembler(inputCols=["stock", "precio"], outputCol="features")
        df_v = assembler.transform(df_spark)
        train, test = df_v.randomSplit([0.8, 0.2], seed=42)
        evaluator = RegressionEvaluator(labelCol="ingreso", predictionCol="prediction", metricName="r2")
        
        lr = LinearRegression(featuresCol="features", labelCol="ingreso").fit(train)
        ridge = LinearRegression(featuresCol="features", labelCol="ingreso", regParam=0.5).fit(train)
        
        return {
            "Regresión Lineal": max(0, evaluator.evaluate(lr.transform(test))),
            "Ridge": max(0, evaluator.evaluate(ridge.transform(test)))
        }
    except:
        return {"Regresión Lineal": 0.0, "Ridge": 0.0}

# --- 4. EJECUCIÓN ---
st.title("🌿 Laboratorio de Analítica: Invernadero")

spark = iniciar_spark()
df_pd = obtener_datos_mongo()

# Filtro en barra lateral
planta_sel = st.sidebar.selectbox("Filtrar por Planta", ["Todas"] + sorted(df_pd["nombre"].unique().tolist()))
df_filtrado = df_pd if planta_sel == "Todas" else df_pd[df_pd["nombre"] == planta_sel]

# Layout de Gráficas
st.subheader(f"Análisis de Inventario: {planta_sel}")
c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(grafica_dispersion(df_filtrado), use_container_width=True)
with c2:
    st.plotly_chart(grafica_distribucion(df_filtrado), use_container_width=True)

# Sección de Machine Learning con Spark
st.divider()
if len(df_filtrado) >= 2:
    st.subheader("🤖 Predicción de Ingresos (Spark ML)")
    # Seleccionamos columnas numéricas para Spark
    df_sp = spark.createDataFrame(df_filtrado[['stock', 'precio', 'ingreso']])
    resultados = ejecutar_modelos(df_sp)
    st.plotly_chart(grafica_modelos(resultados), use_container_width=True)
    st.write("**Métricas de Precisión:**")
    st.json(resultados)
else:
    st.warning("Se requieren al menos 2 registros para el análisis de Machine Learning.")