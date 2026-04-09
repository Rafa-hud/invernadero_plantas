import sys
import os
import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import logging
from io import BytesIO

# --- 0. SILENCIAR ADVERTENCIAS DE TERMINAL ---
logging.getLogger("streamlit.runtime.scriptrunner_utils").setLevel(logging.ERROR)

# --- 1. CONFIGURACIÓN DE RUTAS (SOLUCIÓN AL ERROR DE RUTA) ---
current_dir = os.path.dirname(os.path.abspath(__file__)) # spark/
project_root = os.path.abspath(os.path.join(current_dir, "..")) # Invernadero_plantas-/

if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Lógica de importación flexible para evitar errores de "Archivo no encontrado"
try:
    try:
        from app.config.mongo_spark_conexion_sinnulos import get_spark_session
    except ImportError:
        from config.mongo_spark_conexion_sinnulos import get_spark_session
except Exception as e:
    st.error(f"❌ Error Crítico: No se pudo localizar el archivo de configuración.")
    st.info(f"Asegúrate de que 'mongo_spark_conexion_sinnulos.py' esté en la carpeta 'config'.")
    st.stop()

# --- 2. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Reporte Excel - Intelligence Plant", layout="wide", page_icon="📊")

@st.cache_resource
def cargar_datos_ventas():
    try:
        spark, df_spark, _ = get_spark_session()
        if df_spark is None:
            return None, None
            
        df = df_spark.toPandas()
        df.columns = [str(c).lower() for c in df.columns]
        
        # Limpieza de datos financieros
        df['precio'] = pd.to_numeric(df['precio'], errors='coerce').fillna(0)
        df['stock'] = pd.to_numeric(df['stock'], errors='coerce').fillna(0)
        df['ingreso'] = df['precio'] * df['stock']
        
        return spark, df
    except Exception as e:
        st.error(f"Error al procesar datos de Spark: {e}")
        return None, None

# --- 3. FUNCIÓN EXCEL (Formato Profesional) ---
def generar_excel_ventas(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_excel = df.copy()
        df_excel.columns = [c.upper() for c in df_excel.columns]
        
        df_excel.to_excel(writer, index=False, sheet_name='Ventas Invernadero')
        
        workbook  = writer.book
        worksheet = writer.sheets['Ventas Invernadero']

        # Formatos Estéticos
        header_fmt = workbook.add_format({
            'bold': True, 
            'bg_color': '#28a745', 
            'font_color': 'white', 
            'border': 1,
            'align': 'center'
        })
        money_fmt = workbook.add_format({'num_format': '$#,##0.00'})
        
        # Aplicar formato a encabezados y ajustar columnas
        for col_num, value in enumerate(df_excel.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
            width = max(len(value), 15)
            worksheet.set_column(col_num, col_num, width)

        # Aplicar formato moneda a columnas de dinero
        for i, col in enumerate(df_excel.columns):
            if any(x in col for x in ['PRECIO', 'INGRESO']):
                worksheet.set_column(i, i, 18, money_fmt)

    return output.getvalue()

# --- 4. INTERFAZ DEL DASHBOARD ---
st.title("📊 Reporte de Ventas: Invernadero Plantas")
st.markdown(f"Generado el: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")

spark, df_pd = cargar_datos_ventas()

if df_pd is not None:
    # KPIs Principales
    kpi1, kpi2, kpi3 = st.columns(3)
    with kpi1:
        st.metric("Ventas Totales Proyectadas", f"${df_pd['ingreso'].sum():,.2f}")
    with kpi2:
        st.metric("Inventario Total", f"{int(df_pd['stock'].sum())} und")
    with kpi3:
        st.metric("Variedades Registradas", len(df_pd))

    st.divider()

    # Gráfica de Barras
    label_col = 'producto' if 'producto' in df_pd.columns else df_pd.columns[0]
    fig = px.bar(
        df_pd.sort_values('ingreso', ascending=False), 
        x=label_col, y='ingreso', color='ingreso',
        labels={'ingreso': 'Ingresos ($)', label_col: 'Planta'},
        template="plotly_dark",
        color_continuous_scale='Greens'
    )
    st.plotly_chart(fig, use_container_width=True)

    # Botón de Descarga Excel
    st.subheader("📥 Exportar a Excel")
    st.info("El archivo incluye formato de moneda y encabezados personalizados.")
    
    excel_data = generar_excel_ventas(df_pd)
    st.download_button(
        label="🟢 Descargar Reporte de Ventas (.xlsx)",
        data=excel_data,
        file_name=f"Ventas_Invernadero_{datetime.date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# --- SIDEBAR ---
with st.sidebar:
    st.header("Opciones del Sistema")
    st.markdown(f"""
        <a href="http://localhost:5000/reportes" target="_self">
            <button style="width:100%; background-color:#28a745; color:white; border:none; padding:10px; border-radius:5px; font-weight:bold; cursor:pointer;">
                🏠 Volver a Intelligence Plant
            </button>
        </a>
    """, unsafe_allow_html=True)
    
    if st.button("Cerrar Conexión Spark"):
        if spark:
            spark.stop()
            st.success("Conexión cerrada.")