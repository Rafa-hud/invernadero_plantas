import sys
import os
import streamlit as st
import importlib.util
import time

# --- BLOQUE DE IMPORTACIÓN DINÁMICA ---
def cargar_conexion_dinamica():
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    path_config = os.path.join(root_path, 'config', 'mongo_spark_conexion_sinnulos.py')
    
    if not os.path.exists(path_config):
        st.error(f"❌ No se encontró el archivo de configuración en: {path_config}")
        st.stop()

    spec = importlib.util.spec_from_file_location("modulo_conexion", path_config)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["modulo_conexion"] = modulo
    spec.loader.exec_module(modulo)
    
    return modulo.get_spark_session

try:
    get_spark_session = cargar_conexion_dinamica()
except Exception as e:
    st.error(f"❌ Error al cargar la conexión: {e}")
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
        # Obtenemos sesión y dataframe
        spark, df, _ = get_spark_session()
        
        # Guardamos la sesión en el estado de Streamlit para poder cerrarla después
        st.session_state['spark_session'] = spark
        
        # Procesamiento Spark
        resultado = df.groupBy("producto") \
                      .agg(sum("ingreso").alias("total_ingreso")) \
                      .orderBy(col("total_ingreso").desc())
                      
        return resultado.toPandas()
    except Exception as e:
        st.error(f"❌ Error en el clúster Spark: {e}")
        return None

# --- RENDERIZADO ---
with st.spinner("🚀 Procesando datos en el clúster..."):
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
    st.warning("⚠️ Sin datos. Verifica la colección en MongoDB.")

# --- SIDEBAR CON CONTROL DE SERVIDOR ---
with st.sidebar:
    st.header("⚙️ Controles del Sistema")
    
    if st.button("🔄 Refrescar Datos"):
        st.cache_data.clear()
        st.rerun()
    
    st.divider()
    
    # Botón para cerrar el servidor de Spark
    if st.button("🛑 Cerrar Servidor Spark", help="Libera los recursos del clúster y detiene el motor de analítica"):
        if 'spark_session' in st.session_state:
            try:
                with st.status("Apagando motor de analítica...", expanded=True) as status:
                    st.write("Cerrando sesión de Spark...")
                    st.session_state['spark_session'].stop() # Comando para cerrar el servidor
                    
                    # Limpiamos el estado
                    del st.session_state['spark_session']
                    st.cache_data.clear()
                    
                    st.write("✅ Servidor detenido con éxito.")
                    status.update(label="Servidor de Spark Cerrado", state="complete", expanded=False)
                
                st.success("Analítica detenida. Puedes cerrar esta pestaña.")
                time.sleep(2)
                st.stop() # Detiene la ejecución de Streamlit
            except Exception as e:
                st.error(f"Error al cerrar Spark: {e}")
        else:
            st.info("No hay ninguna sesión de Spark activa para cerrar.")