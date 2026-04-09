import sys
import os
import streamlit as st
import pandas as pd
import plotly.express as px
from fpdf import FPDF
import base64

# --- 1. CONFIGURACIÓN DE RUTAS ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# --- 2. IMPORTACIONES DINÁMICAS ---
try:
    from app.config.mongo_spark_conexion_sinnulos import get_spark_session
    from pyspark.ml.feature import VectorAssembler
    from pyspark.ml.regression import LinearRegression
    from pyspark.ml.evaluation import RegressionEvaluator
except ImportError as e:
    st.error(f"❌ Error de configuración: {e}")
    st.stop()

# --- 3. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Reporte Maestro - Invernadero", layout="wide", page_icon="📄")

@st.cache_resource
def obtener_datos_maestros():
    try:
        spark, df_spark, _ = get_spark_session()
        df_plants = df_spark.toPandas()
        df_plants.columns = [str(c).lower() for c in df_plants.columns]
        columnas_num = ['precio', 'stock', 'ingreso']
        for col in columnas_num:
            if col in df_plants.columns:
                df_plants[col] = pd.to_numeric(df_plants[col], errors='coerce').fillna(0)
        return spark, df_spark, df_plants
    except Exception as e:
        st.error(f"Error al conectar con el clúster: {e}")
        st.stop()

# --- 4. FUNCIÓN PARA GENERAR PDF ---
def generar_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="Reporte Técnico - Intelligence Plant", ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.ln(10)
    pdf.cell(200, 10, txt=f"Total de variedades: {len(df)}", ln=True)
    pdf.cell(200, 10, txt=f"Valor total inventario: ${df['ingreso'].sum():,.2f}", ln=True)
    pdf.ln(10)
    
    # Encabezados de tabla
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(60, 10, "Producto", 1)
    pdf.cell(40, 10, "Precio", 1)
    pdf.cell(40, 10, "Stock", 1)
    pdf.cell(40, 10, "Ingreso", 1)
    pdf.ln()
    
    # Datos
    pdf.set_font("Arial", size=10)
    for i, row in df.iterrows():
        # Limitamos a los primeros 20 para el PDF
        if i > 20: break 
        prod_nom = str(row.get('producto', row.get('nombre', 'N/A')))[:25]
        pdf.cell(60, 10, prod_nom, 1)
        pdf.cell(40, 10, f"${row['precio']:,.2f}", 1)
        pdf.cell(40, 10, str(int(row['stock'])), 1)
        pdf.cell(40, 10, f"${row['ingreso']:,.2f}", 1)
        pdf.ln()
    
    return pdf.output(dest='S').encode('latin-1')

# --- 5. EJECUCIÓN Y UI ---
st.title("📄 Reporte Técnico de Operaciones")
spark, df_sp, df_pd = obtener_datos_maestros()

# Botones de Acción en el Header
col_btn1, col_btn2 = st.columns([1, 5])
with col_btn1:
    pdf_bytes = generar_pdf(df_pd)
    st.download_button(
        label="📥 Descargar PDF",
        data=pdf_bytes,
        file_name="reporte_invernadero.pdf",
        mime="application/pdf"
    )

# KPIs
c1, c2, c3 = st.columns(3)
with c1: st.metric("Variedades", len(df_pd))
with c2: st.metric("Valor Total", f"${df_pd['ingreso'].sum():,.2f}")
with c3: st.metric("Stock Global", f"{int(df_pd['stock'].sum())}")

# Gráficas
st.divider()
col_left, col_right = st.columns(2)
label_col = 'producto' if 'producto' in df_pd.columns else df_pd.columns[0]

with col_left:
    st.plotly_chart(px.pie(df_pd, values='ingreso', names=label_col, template="plotly_dark", title="Distribución de Valor"), use_container_width=True)
with col_right:
    st.plotly_chart(px.scatter(df_pd, x="stock", y="precio", size="ingreso", color="ingreso", template="plotly_dark", title="Densidad Stock vs Precio"), use_container_width=True)

# Sidebar de Navegación
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/628/628283.png", width=100)
    st.header("Control de Navegación")
    
    # BOTÓN PARA REGRESAR AL DASHBOARD DE FLASK
    st.markdown(f"""
        <a href="http://localhost:5000/reportes" target="_self">
            <button style="width:100%; background-color:#28a745; color:white; border:none; padding:10px; border-radius:5px; font-weight:bold; cursor:pointer;">
                🏠 Volver al Dashboard
            </button>
        </a>
    """, unsafe_allow_html=True)
    
    st.divider()
    if st.button("🛑 Cerrar Sesión Spark"):
        spark.stop()
        st.success("Recursos liberados.")

# --- 6. ML DIAGNÓSTICO ---
st.divider()
st.subheader("🤖 Diagnóstico de IA (Spark ML)")
with st.expander("Ver métricas de precisión", expanded=True):
    try:
        assembler = VectorAssembler(inputCols=["stock", "precio"], outputCol="features", handleInvalid="skip")
        df_v = assembler.transform(df_sp)
        train, test = df_v.randomSplit([0.8, 0.2], seed=42)
        lr = LinearRegression(featuresCol="features", labelCol="ingreso").fit(train)
        evaluator = RegressionEvaluator(labelCol="ingreso", predictionCol="prediction", metricName="r2")
        r2 = evaluator.evaluate(lr.transform(test))
        st.write(f"Precisión del modelo (R²): **{max(0, r2):.4f}**")
    except:
        st.write("Datos insuficientes para el modelo ML.")