import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os

# --- 1. CORRECCIÓN DE RUTAS DE ALTA PRIORIDAD ---
# Obtenemos la ruta absoluta de la carpeta raíz 'Invernadero_plantas-'
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))

# Insertamos la raíz al principio de sys.path para que encuentre el paquete 'app'
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# --- 2. SOLUCIÓN COMPATIBILIDAD PYTHON 3.12 ---
try:
    import setuptools
except ImportError:
    st.error("Falta la librería 'setuptools'. Ejecuta: pip install setuptools")

# --- 3. IMPORTACIONES DINÁMICAS (CORREGIDO PARA APP/CONFIG) ---
try:
    from pyspark.ml.clustering import KMeans
    from pyspark.ml.evaluation import ClusteringEvaluator
    
    # IMPORTANTE: Ahora importamos desde app.config
    from app.config.mongo_spark_conexion_sinnulos import get_spark_session
    
except Exception as e:
    st.error(f"❌ Error de importación: {e}")
    # Mostramos la ruta de búsqueda para confirmar que subió correctamente a la raíz
    st.info(f"Ruta raíz detectada: {root_dir}")
    st.stop()

# --- 4. CONFIGURACIÓN DE INTERFAZ ---
st.set_page_config(page_title="Invernadero Pro - ML", layout="wide")
st.title("🌿 Análisis de Segmentación de Plantas")
st.markdown("Clasificación inteligente de inventario basada en Spark ML y MongoDB Atlas.")

# Parámetros en la barra lateral
k_value = st.sidebar.slider("Cantidad de Clusters (K)", 2, 6, 3)

# --- 5. PIPELINE DE DATOS ---
@st.cache_resource
def ejecutar_pipeline_kmeans(k):
    # Obtenemos la sesión configurada y el dataframe vectorizado
    spark, df_full, df_vector = get_spark_session()

    # Entrenamiento del modelo KMeans
    kmeans = KMeans(k=k, seed=1, featuresCol="features", predictionCol="prediction")
    model = kmeans.fit(df_vector)
    result = model.transform(df_vector)

    # Evaluación (Silhouette Score)
    evaluator = ClusteringEvaluator()
    silhouette = evaluator.evaluate(result)

    # Convertir a Pandas para visualización
    pdf = result.select("producto", "precio", "stock", "ingreso", "prediction").toPandas()
    
    return pdf, silhouette

# --- 6. RENDERIZADO DEL DASHBOARD ---
try:
    with st.spinner("Procesando ADN de datos desde MongoDB Atlas..."):
        data, score = ejecutar_pipeline_kmeans(k_value)

    # KPIs Principales
    m1, m2, m3 = st.columns(3)
    m1.metric("Plantas en Inventario", len(data))
    m2.metric("Valor Total", f"${data['ingreso'].sum():,.2f}")
    m3.metric("Precisión (Silhouette)", f"{score:.4f}")

    # Gráficos
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("📍 Dispersión: Precio vs Ingreso")
        fig_2d = px.scatter(
            data, x="precio", y="ingreso", color="prediction",
            size="stock", hover_data=["producto"],
            template="plotly_dark", 
            color_continuous_scale="Viridis"
        )
        st.plotly_chart(fig_2d, use_container_width=True)

    with col_b:
        st.subheader("📦 Análisis 3D: Inventario")
        fig_3d = px.scatter_3d(
            data, x="precio", y="stock", z="ingreso",
            color="prediction", hover_name="producto",
            template="plotly_dark"
        )
        st.plotly_chart(fig_3d, use_container_width=True)

    # Tabla resumen
    st.divider()
    st.subheader("📝 Resumen de Segmentos")
    resumen = data.groupby("prediction").agg({
        'ingreso': 'mean',
        'stock': 'sum',
        'producto': 'count'
    }).rename(columns={'ingreso': 'Ingreso Promedio', 'stock': 'Stock Total', 'producto': 'Variedad'})
    
    st.table(resumen.style.format("${:,.2f}", subset=['Ingreso Promedio']))

except Exception as e:
    st.error(f"Error crítico: {e}")
    st.info("Verifica que app/config/__init__.py esté vacío.")