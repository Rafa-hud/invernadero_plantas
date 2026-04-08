import streamlit as st
import pandas as pd
import plotly.express as px
from pymongo import MongoClient
from pyspark.sql import SparkSession
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.regression import LinearRegression
from pyspark.ml.evaluation import RegressionEvaluator

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Invernadero Pro Analytics", layout="wide")

@st.cache_resource
def iniciar_spark():
    spark = SparkSession.builder.appName("InvernaderoAnalytics").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark

# --- 2. FUNCIÓN DE LIMPIEZA CRÍTICA ---
def normalizar_dataframe(df):
    """Convierte todas las columnas a minúsculas y asegura tipos numéricos."""
    if df.empty:
        return df
    # 1. Nombres de columnas a minúsculas para evitar KeyError: 'total' vs 'Total'
    df.columns = [str(c).lower() for c in df.columns]
    
    # 2. Asegurar que campos clave sean numéricos
    columnas_num = ['precio', 'stock', 'total', 'ingreso']
    for col in columnas_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # 3. Crear 'ingreso' si no existe (precio * stock)
    if 'ingreso' not in df.columns and 'precio' in df.columns and 'stock' in df.columns:
        df['ingreso'] = df['precio'] * df['stock']
        
    return df

def obtener_datos_mongo():
    uri = "mongodb+srv://admin:Emmanuel123@cluster0.cerffq3.mongodb.net/?appName=Cluster0"
    client = MongoClient(uri)
    db = client.get_database('invernadero_db')
    
    # Intentar obtener colecciones (manejando variaciones de nombre)
    col_names = db.list_collection_names()
    
    # Buscar 'plants' o 'Plantas'
    p_name = 'plants' if 'plants' in col_names else 'Plantas'
    o_name = 'orders' if 'orders' in col_names else 'Órdenes'
    
    df_plants = pd.DataFrame(list(db[p_name].find()))
    df_orders = pd.DataFrame(list(db[o_name].find()))
    
    client.close()

    # Normalizar ambos DataFrames inmediatamente
    df_plants = normalizar_dataframe(df_plants)
    df_orders = normalizar_dataframe(df_orders)

    if df_plants.empty:
        st.error(f"❌ No se encontraron datos en la colección '{p_name}'")
        st.stop()
        
    return df_plants, df_orders

# --- 3. LÓGICA DE MACHINE LEARNING ---
def ejecutar_modelos(spark, df):
    try:
        # Usamos las columnas ya normalizadas a minúsculas
        df_sp = spark.createDataFrame(df[['stock', 'precio', 'ingreso']])
        assembler = VectorAssembler(inputCols=["stock", "precio"], outputCol="features")
        df_v = assembler.transform(df_sp)
        train, test = df_v.randomSplit([0.8, 0.2], seed=42)
        
        lr = LinearRegression(featuresCol="features", labelCol="ingreso").fit(train)
        evaluator = RegressionEvaluator(labelCol="ingreso", predictionCol="prediction", metricName="r2")
        return {"Regresión Lineal": max(0, evaluator.evaluate(lr.transform(test)))}
    except:
        return {"Regresión Lineal": 0.0}

# --- 4. EJECUCIÓN DEL DASHBOARD ---
st.title("🌿 Laboratorio de Analítica: Invernadero")

spark = iniciar_spark()
df_plants, df_orders = obtener_datos_mongo()

# KPIs Superiores
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Total Plantas", len(df_plants))
with c2:
    # Aquí ya no fallará porque normalizamos a minúsculas
    v_total = df_orders['total'].sum() if 'total' in df_orders.columns else 0
    st.metric("Ventas Totales", f"${v_total:,.2f}")
with c3:
    st.metric("Stock Global", int(df_plants['stock'].sum()))

# Gráficas
col_left, col_right = st.columns(2)
with col_left:
    fig_disp = px.scatter(df_plants, x="stock", y="ingreso", color="nombre", 
                         title="Relación Stock vs Ingreso", template="plotly_dark")
    st.plotly_chart(fig_disp, use_container_width=True)

with col_right:
    if 'total' in df_orders.columns and not df_orders.empty:
        fig_ventas = px.histogram(df_orders, x="total", title="Distribución de Montos de Venta", 
                                 template="plotly_dark", color_discrete_sequence=['#0d6efd'])
        st.plotly_chart(fig_ventas, use_container_width=True)

# Sección Spark
st.divider()
st.subheader("🤖 Predicción de Ingresos (Spark ML)")
resultados = ejecutar_modelos(spark, df_plants)
st.json(resultados)