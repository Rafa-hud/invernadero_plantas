import sys
import os
import streamlit as st
import pandas as pd

# --- 1. CONFIGURACIÓN DE RUTAS Y ENTORNO ---
# Forzamos la ruta raíz para encontrar 'config', 'ml_algorithms' y 'processing'
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Solución para Python 3.12 (setuptools es necesario para Spark)
try:
    import setuptools
except ImportError:
    st.error("Falta 'setuptools'. Ejecuta: pip install setuptools")

# --- 2. IMPORTACIONES DINÁMICAS ---
try:
    from config.mongo_spark_conexion_sinnulos import get_spark_session
    # Asegúrate de que estos archivos existan en tus carpetas ml_algorithms y processing
    from ml_algorithms.regresion_analytics_modelos_dash import ejecutar_modelos
    from processing.regresion_analytics_graficos_dash import (
        grafica_dispersion,
        grafica_distribucion,
        grafica_precio_vs_ingreso,
        grafica_modelos
    )
except ImportError as e:
    st.error(f"❌ Error al importar módulos internos: {e}")
    st.stop()

# --- 3. CONFIGURACIÓN DEL DASHBOARD ---
st.set_page_config(
    page_title="Analytics Modelos de Regresión",
    layout="wide",
    page_icon="📈"
)

st.title("🚀 Plataforma de Analítica Predictiva con Spark")
st.markdown("Comparativa de modelos de Machine Learning sobre inventario de plantas.")

# --- 4. CONEXIÓN A SPARK (Cacheada para estabilidad) ---
@st.cache_resource
def iniciar_spark():
    # get_spark_session devuelve: spark, df_full, df_vector
    spark, _, df = get_spark_session()
    return spark, df

try:
    spark, df = iniciar_spark()
except Exception as e:
    st.error(f"Error al conectar con MongoDB Atlas: {e}")
    st.stop()

# --- 5. FILTROS INTERACTIVOS ---
st.sidebar.header("🛠️ Filtros de Datos")

# Obtenemos lista de productos únicos desde Spark
try:
    productos_list = df.select("producto").distinct().toPandas()["producto"].tolist()
    producto_sel = st.sidebar.selectbox(
        "Seleccionar Producto",
        ["Todos"] + sorted(productos_list)
    )

    # Aplicar filtro
    if producto_sel != "Todos":
        df_filtrado = df.filter(df.producto == producto_sel)
    else:
        df_filtrado = df

    # IMPORTANTE: Persistir en memoria para no re-leer de Atlas en cada gráfica
    df_filtrado = df_filtrado.cache()
    df_pandas = df_filtrado.toPandas()

except Exception as e:
    st.error(f"Error al procesar filtros: {e}")
    st.stop()

# --- 6. VISUALIZACIONES DE DATOS (AED) ---
st.subheader("📊 Análisis Exploratorio de Datos")

if not df_pandas.empty:
    col1, col2 = st.columns(2)

    with col1:
        # Nota: Asegúrate que esta función use la columna 'stock' y no 'cantidad'
        st.markdown("**Relación Stock vs Ingreso**")
        fig1 = grafica_dispersion(df_pandas)
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        st.markdown("**Relación Precio vs Ingreso**")
        fig2 = grafica_precio_vs_ingreso(df_pandas)
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("**Distribución de Ingresos Totales**")
    fig3 = grafica_distribucion(df_pandas)
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.warning("No hay datos disponibles para el filtro seleccionado.")

# --- 7. EJECUCIÓN DE MACHINE LEARNING ---
st.divider()
st.subheader("🤖 Entrenamiento de Modelos de Regresión")

if st.button("Ejecutar Comparativa de Modelos"):
    with st.spinner("Entrenando modelos en Spark..."):
        try:
            # Esta función debe devolver un DataFrame de resultados y las predicciones
            resultados, predicciones = ejecutar_modelos(df_filtrado)
            
            # Gráfica de comparación de R2
            st.plotly_chart(grafica_modelos(resultados), use_container_width=True)

            # Tabla de métricas
            st.subheader("📋 Métricas de Evaluación (R² / RMSE)")
            st.dataframe(resultados, use_container_width=True)
            
            st.success("Modelos entrenados exitosamente.")
        except Exception as e:
            st.error(f"Error durante el entrenamiento: {e}")
            st.info("Revisa que la columna 'stock' esté siendo procesada correctamente en ml_algorithms.")

# Botón para limpiar caché y cerrar sesión si es necesario
if st.sidebar.button("Cerrar Sesión Spark"):
    spark.stop()
    st.sidebar.success("Sesión cerrada.")