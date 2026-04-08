import plotly.express as px
import plotly.graph_objects as go

def grafica_dispersion(df_pandas):
    """Relación Stock vs Ingreso"""
    fig = px.scatter(
        df_pandas, 
        x="stock", 
        y="ingreso", 
        color="producto",
        title="Relación Stock vs Ingreso",
        labels={"stock": "Stock (Unidades)", "ingreso": "Ingreso ($)"},
        template="plotly_dark"
    )
    return fig

def grafica_precio_vs_ingreso(df_pandas):
    """Relación Precio vs Ingreso"""
    fig = px.scatter(
        df_pandas, 
        x="precio", 
        y="ingreso", 
        color="producto",
        size="stock",
        title="Relación Precio vs Ingreso (Tamaño = Stock)",
        labels={"precio": "Precio ($)", "ingreso": "Ingreso ($)"},
        template="plotly_dark"
    )
    return fig

def grafica_distribucion(df_pandas):
    """Histograma de Ingresos"""
    fig = px.histogram(
        df_pandas, 
        x="ingreso", 
        nbins=30,
        title="Distribución de Ingresos",
        labels={"ingreso": "Ingreso ($)"},
        color_discrete_sequence=['#00CC96'],
        template="plotly_dark"
    )
    return fig

def grafica_modelos(df_resultados):
    """Comparativa de R2 de los modelos entrenados"""
    # Ordenar resultados para mejor visualización
    df_resultados = df_resultados.sort_values(by="R2_Score", ascending=False)
    
    fig = px.bar(
        df_resultados, 
        x="Modelo", 
        y="R2_Score",
        color="R2_Score",
        title="Comparativa de Rendimiento (R² Score)",
        labels={"R2_Score": "Precisión (R²)", "Modelo": "Algoritmo"},
        color_continuous_scale=px.colors.sequential.Viridis,
        template="plotly_dark"
    )
    
    # Añadir línea de referencia en 1.0 (perfección)
    fig.add_hline(y=1.0, line_dash="dash", line_color="white", annotation_text="Ideal")
    
    return fig