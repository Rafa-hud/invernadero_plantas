import sys
import os
import streamlit as st
import importlib.util
import time

# --- BLOQUE DE IMPORTACIÓN DINÁMICA (ACTUALIZADO PARA LA NUEVA ESTRUCTURA) ---
def cargar_conexion_dinamica():
    # 1. Obtenemos la raíz (Invernadero_plantas-) subiendo un nivel desde /spark
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    # 2. RUTA CORREGIDA: Ahora incluimos 'app' en el camino
    path_config = os.path.join(root_path, 'app', 'config', 'mongo_spark_conexion_sinnulos.py')
    
    if not os.path.exists(path_config):
        # Mostramos la ruta exacta en pantalla para depuración si falla
        st.error(f"❌ No se encontró el archivo de configuración en: {path_config}")
        st.info("Verifica que la carpeta 'config' esté dentro de 'app'.")
        st.stop()

    # 3. Importación segura del módulo
    spec = importlib.util.spec_from_file_location("conexion_db", path_config)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["conexion_db"] = modulo 
    spec.loader.exec_module(modulo)
    
    # Retornamos la función que definimos en el archivo de conexión
    return modulo.get_spark_session

try:
    get_spark_session = cargar_conexion_dinamica()
except Exception as e:
    st.error(f"❌ Error crítico de rutas: {e}")
    st.stop()

# --- IMPORTACIONES DE SPARK ---
from pyspark.sql.functions import sum, col

# --- CONFIGURACIÓN DE INTERFAZ ---
st.set_page_config(page_title="Dashboard Invernadero", page_icon="🌱", layout="wide")

st.title("🌱 Dashboard Analítico del Invernadero")
st.subheader("Ingresos Potenciales por Especie (MapReduce)")

# --- LÓGICA DE DATOS ---
@st.cache_data(show_spinner=False)
def obtener_datos_mapreduce():
    try:
        # Obtenemos sesión y dataframe (ahora retorna 3 valores: spark, df, df_vector)
        spark, df, _ = get_spark_session()
        
        # Guardamos la sesión para poder cerrarla después
        st.session_state['spark_session'] = spark
        
        # Procesamiento Spark: Agrupación por producto (Map) y suma de ingresos (Reduce)
        resultado = df.groupBy("producto") \
                      .agg(sum("ingreso").alias("total_ingreso")) \
                      .orderBy(col("total_ingreso").desc())
                      
        return resultado.toPandas()
    except Exception as e:
        st.error(f"❌ Error en el clúster Spark: {e}")
        return None

# --- RENDERIZADO ---
with st.spinner("🚀 Procesando ADN de Datos en el clúster..."):
    datos_grafica = obtener_datos_mapreduce()

if datos_grafica is not None and not datos_grafica.empty:
    total_general = datos_grafica['total_ingreso'].sum()
    st.metric("Ingreso Total Proyectado", f"${total_general:,.2f}")

    col1, col2 = st.columns([1, 2])
    with col1:
        st.write("### 📋 Tabla de Resultados")
        st.dataframe(datos_grafica.style.format({"total_ingreso": "${:,.2f}"}), use_container_width=True)

    with col2:
        st.write("### 📊 Gráfica de Ingresos")
        st.bar_chart(data=datos_grafica, x="producto", y="total_ingreso", color="#28a745")
else:
    st.warning("⚠️ Sin datos. Verifica la conexión con MongoDB Atlas.")

# --- SIDEBAR CON CONTROL DE SERVIDOR ---
with st.sidebar:
    st.header("⚙️ Controles del Sistema")
    
    if st.button("🔄 Refrescar Datos"):
        st.cache_data.clear()
        st.rerun()
    
    st.divider()
    
    if st.button("🛑 Cerrar Servidor Spark"):
        if 'spark_session' in st.session_state:
            try:
                st.session_state['spark_session'].stop() 
                del st.session_state['spark_session']
                st.cache_data.clear()
                st.success("✅ Servidor detenido. Puedes cerrar esta pestaña.")
                st.stop() 
            except Exception as e:
                st.error(f"Error al cerrar Spark: {e}")