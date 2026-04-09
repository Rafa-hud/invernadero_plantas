import sys
import os
import streamlit as st
import pandas as pd
import plotly.express as px

# --- 1. CONFIGURACIÓN DE RUTAS Y ENTORNO ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))

if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# --- 2. IMPORTACIONES DINÁMICAS (CORREGIDO PARA APP/CONFIG) ---
try:
    # Usamos tu conexión centralizada
    from app.config.mongo_spark_conexion_sinnulos import get_spark_session
    from pyspark.ml.feature import VectorAssembler
    from pyspark.ml.regression import LinearRegression
    from pyspark.ml.evaluation import RegressionEvaluator
except ImportError as e:
    st.error(f"❌ Error de configuración: {e}")
    st.stop()

# --- 3. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Lab de Gráficos - Invernadero", layout="wide", page_icon="🧪")

# --- 4. FUNCIONES DE VISUALIZACIÓN ---
def grafica_dispersion(df):
    label_col = 'producto' if 'producto' in df.columns else df.columns[0]
    return px.scatter(df, x="stock", y="ingreso", color=label_col, size="precio",
                     hover_data=["precio"], template="plotly_dark", 
                     title="Relación Stock vs Ingreso", color_discrete_sequence=px.colors.qualitative.Prism)

def grafica_distribucion(df):
    return px.histogram(df, x="ingreso", nbins=15,
                       template="plotly_dark", title="Distribución de Ingresos Totales",
                       color_discrete_sequence=['#20c997'])

def grafica_modelos(resultados):
    df_modelos = pd.DataFrame(list(resultados.items()), columns=["Modelo", "R2"])
    return px.bar(df_modelos, x="Modelo", y="R2", color="Modelo",
                 template="plotly_dark", title="Precisión de Modelos Predictivos (R²)")

# --- 5. LÓGICA DE DATOS ---
@st.cache_resource
def obtener_datos_laboratorio():
    try:
        # Obtenemos sesión y datos
        spark, df_spark, _ = get_spark_session()
        
        # Convertimos a Pandas para las gráficas de Plotly
        pdf = df_spark.toPandas()
        pdf.columns = [str(c).lower() for c in pdf.columns]
        
        # Aseguramos que existan datos numéricos
        pdf['precio'] = pd.to_numeric(pdf['precio'], errors='coerce').fillna(0)
        pdf['stock'] = pd.to_numeric(pdf['stock'], errors='coerce').fillna(0)
        pdf['ingreso'] = pdf['precio'] * pdf['stock']
        
        return spark, df_spark, pdf
    except Exception as e:
        st.error(f"Error en el clúster: {e}")
        st.stop()

def ejecutar_modelos_lab(df_spark):
    try:
        assembler = VectorAssembler(inputCols=["stock", "precio"], outputCol="features", handleInvalid="skip")
        df_v = assembler.transform(df_spark)
        train, test = df_v.randomSplit([0.8, 0.2], seed=42)
        evaluator = RegressionEvaluator(labelCol="ingreso", predictionCol="prediction", metricName="r2")
        
        lr = LinearRegression(featuresCol="features", labelCol="ingreso").fit(train)
        ridge = LinearRegression(featuresCol="features", labelCol="ingreso", regParam=0.5).fit(train)
        
        return {
            "Regresión Lineal": max(0, evaluator.evaluate(lr.transform(test))),
            "Regresión Ridge": max(0, evaluator.evaluate(ridge.transform(test)))
        }
    except:
        return {"Regresión Lineal": 0.0, "Regresión Ridge": 0.0}

# --- 6. EJECUCIÓN ---
st.title("🧪 Lab de Gráficos Experimentales")
st.markdown("Espacio de visualización avanzada para el análisis de correlación profunda.")

spark, df_sp, df_pd = obtener_datos_laboratorio()

# Filtro en barra lateral
label_col = 'producto' if 'producto' in df_pd.columns else df_pd.columns[0]
planta_sel = st.sidebar.selectbox("Filtrar por Especie", ["Todas"] + sorted(df_pd[label_col].unique().tolist()))
df_filtrado = df_pd if planta_sel == "Todas" else df_pd[df_pd[label_col] == planta_sel]

# Layout de Gráficas
c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(grafica_dispersion(df_filtrado), use_container_width=True)
with c2:
    st.plotly_chart(grafica_distribucion(df_filtrado), use_container_width=True)

# Sección de Machine Learning
st.divider()
if len(df_filtrado) >= 2:
    st.subheader("🤖 Análisis de Regresión en Tiempo Real")
    # Convertimos de nuevo a Spark solo el fragmento filtrado
    df_sp_filtrado = spark.createDataFrame(df_filtrado[['stock', 'precio', 'ingreso']])
    resultados = ejecutar_modelos_lab(df_sp_filtrado)
    st.plotly_chart(grafica_modelos(resultados), use_container_width=True)
else:
    st.warning("Se requieren más datos para ejecutar modelos de regresión sobre esta planta.")

# --- SIDEBAR DE NAVEGACIÓN ---
with st.sidebar:
    st.header("Navegación")
    
    # BOTÓN PARA REGRESAR AL DASHBOARD DE FLASK
    st.markdown(f"""
        <a href="http://localhost:5000/reportes" target="_self">
            <button style="width:100%; background-color:#20c997; color:white; border:none; padding:10px; border-radius:5px; font-weight:bold; cursor:pointer;">
                🏠 Volver a Intelligence Plant
            </button>
        </a>
    """, unsafe_allow_html=True)
    
    st.divider()
    if st.button("🛑 Liberar Recursos Spark"):
        spark.stop()
        st.success("Sesión cerrada.")