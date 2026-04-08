from pyspark.ml.feature import VectorAssembler, PolynomialExpansion
from pyspark.ml.regression import LinearRegression
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.tuning import CrossValidator, ParamGridBuilder
import pandas as pd

def ejecutar_modelos(df):
    """
    Ejecuta la comparativa de modelos de regresión con limpieza de columnas para evitar errores.
    """
    # 1. LIMPIEZA PREVENTIVA: Si la columna 'features' ya existe, la eliminamos
    if "features" in df.columns:
        df = df.drop("features")
    if "poly_features" in df.columns:
        df = df.drop("poly_features")

    # Aseguramos que no haya nulos en stock o precio
    df = df.filter((df.stock.isNotNull()) & (df.precio.isNotNull()))
    
    # División del dataset
    train, test = df.randomSplit([0.8, 0.2], seed=42)

    # 2. PREPARACIÓN (Usamos un nombre único para evitar conflictos si fuera necesario)
    assembler_multiple = VectorAssembler(inputCols=["stock", "precio"], outputCol="features")
    train_multiple = assembler_multiple.transform(train)
    test_multiple = assembler_multiple.transform(test)

    # Evaluador
    evaluator = RegressionEvaluator(labelCol="ingreso", predictionCol="prediction", metricName="r2")
    dict_resultados = {}

    # --- MODELO 1: LINEAL MÚLTIPLE ---
    lr = LinearRegression(featuresCol="features", labelCol="ingreso")
    model_lr = lr.fit(train_multiple)
    pred_lr = model_lr.transform(test_multiple)
    dict_resultados["Lineal Multiple"] = evaluator.evaluate(pred_lr)

    # --- MODELO 2: RIDGE ---
    ridge = LinearRegression(featuresCol="features", labelCol="ingreso", regParam=0.5, elasticNetParam=0)
    model_ridge = ridge.fit(train_multiple)
    pred_ridge = model_ridge.transform(test_multiple)
    dict_resultados["Ridge"] = evaluator.evaluate(pred_ridge)

    # --- MODELO 3: POLINÓMICA ---
    # Aquí también limpiamos antes de transformar por si acaso
    poly = PolynomialExpansion(inputCol="features", outputCol="poly_features", degree=2)
    train_poly = poly.transform(train_multiple)
    test_poly = poly.transform(test_multiple)

    lr_poly = LinearRegression(featuresCol="poly_features", labelCol="ingreso")
    model_poly = lr_poly.fit(train_poly)
    pred_poly = model_poly.transform(test_poly)
    dict_resultados["Polinomial"] = evaluator.evaluate(pred_poly)

    # --- MODELO 4: CROSS VALIDATION ---
    lr_cv = LinearRegression(featuresCol="features", labelCol="ingreso")
    paramGrid = ParamGridBuilder().addGrid(lr_cv.regParam, [0.1, 1.0]).build()
    cv = CrossValidator(estimator=lr_cv, estimatorParamMaps=paramGrid, evaluator=evaluator, numFolds=2)
    
    try:
        model_cv = cv.fit(train_multiple)
        pred_cv = model_cv.transform(test_multiple)
        dict_resultados["Cross Validation"] = evaluator.evaluate(pred_cv)
    except:
        dict_resultados["Cross Validation"] = 0.0

    # Formatear salida
    df_resultados = pd.DataFrame(list(dict_resultados.items()), columns=["Modelo", "R2_Score"])
    
    return df_resultados, pred_poly

#streamlit run spark/07_dashboard_regresion_models.py