# Refacciones Analytics

Dashboard de inventario y logística desarrollado con Python y asistencia de IA. Convierte fuentes separadas en una vista para revisar prioridades, demanda, tránsitos y calidad de datos.

**Esta versión de portafolio utiliza exclusivamente datos ficticios**, inventados mediante código. No contiene registros reales, datos anonimizados, documentos internos ni credenciales. No se conecta a sistemas de una empresa.

## Qué permite decidir

| Pregunta | Qué muestra | Para qué sirve |
| --- | --- | --- |
| ¿Qué piezas atender primero? | Cobertura en meses y umbral de 4 meses | Priorizar la revisión de abastecimiento |
| ¿Dónde está el capital? | Inventario por familia y nivel de consumo | Revisar concentración y posibles excesos |
| ¿Qué se está solicitando? | Demanda mensual, estados y mapa de calor por pieza | Identificar solicitudes y pedidos pendientes |
| ¿Qué ingresos necesitan seguimiento? | Estados logísticos y fechas de llegada | Revisar retrasos o fechas sin confirmar |
| ¿Podemos confiar en las cifras? | Duplicados, faltantes y trazabilidad de incidencias | Corregir datos antes de decidir |

Incluye filtros compartidos, gráficos interactivos, cantidades con unidades, importes MXN/USD y explicaciones de problema, solución y decisión. La revisión de calidad siempre considera todas las fuentes, no solo la selección.

## Ejecutar la demostración

Requiere Python 3.12. Desde esta carpeta, sin Excel ni claves:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

En Linux/macOS, sustituir `.\.venv\Scripts\python.exe` por `.venv/bin/python`.

Los datos se generan en memoria en [src/demo_data.py](src/demo_data.py): 43 filas de inventario (40 códigos únicos utilizables), 120 solicitudes y 50 movimientos logísticos. Incluyen errores deliberados para demostrar su detección. Las fechas son fijas; los resultados no representan una operación actual.

## Lógica principal y límites

- **Cobertura = inventario actual / demanda mensual. Prioridad si es estrictamente menor que 4 meses.** Cuatro meses exactos no activa la regla. Con demanda positiva y cero existencias, la cobertura es cero.
- Sin consumo, datos inválidos o códigos ambiguos, la cobertura no se calcula. Un dato desconocido no se reemplaza por cero.
- Faltante bruto = máximo de cero y `(demanda mensual × meses de entrega) − inventario`. No descuenta pedidos en camino ni equivale a una orden de compra.
- Los filtros relacionan inventario, pedidos y tránsitos por código. Un duplicado no hereda atributos de una fila elegida arbitrariamente.
- ABC y propuestas de compra son etiquetas/valores de entrada. En esta demo son inventados; la app no calcula un ABC 80/15/5 ni autoriza compras.
- KMeans e Isolation Forest son exploratorios: agrupan comportamientos y señalan casos para revisar. No predicen desabasto ni garantizan ahorro.

## Tecnologías y aportaciones

- **Python, pandas y NumPy:** limpieza, reglas de negocio, relaciones entre fuentes y cálculo de indicadores.
- **Streamlit y Plotly:** aplicación web, filtros, tablas y visualizaciones interactivas.
- **openpyxl:** adaptadores de lectura XLSX conservados para uso local controlado; la demo no los utiliza.
- **scikit-learn:** estandarización, KMeans e Isolation Forest con semilla reproducible y registros completos.
- **unittest y Streamlit AppTest:** pruebas de reglas, gráficos, datos ficticios y recorrido completo del dashboard.

**Trabajo humano:** definición del problema logístico, elección y validación de prioridades, regla de cobertura menor a cuatro meses, decisiones sobre filtros, unidades, trazabilidad y presentación para usuarios del negocio; revisión mediante retroalimentación.

**Asistencia de IA:** apoyo para implementar código, preparar visualizaciones, proponer comprobaciones y redactar documentación. La IA no reemplaza el criterio operativo ni la validación de las fuentes. Keras, PyTorch, Random Forest y SARSA son posibilidades futuras, no tecnologías implementadas en esta versión.

## Pruebas y publicación

Con el entorno activado:

```text
python -m unittest discover -s tests -p "test_*.py" -v
python -m unittest discover -s tests -p integration_dashboard.py -v
python scripts/check_publication.py
```

El verificador de publicación usa una lista explícita de archivos permitidos, rechaza archivos adicionales y busca patrones comunes de secretos y rutas personales. Es una defensa adicional, no una certificación de seguridad. Para generar un ZIP solo con los archivos revisados:

```text
python scripts/check_publication.py --zip ../refacciones-analytics-publico.zip
```

El ZIP es para transportar el proyecto: **extraerlo y subir su contenido**, no únicamente el ZIP. No subir la carpeta original de trabajo. GitHub aloja el código; publicar el repositorio no despliega automáticamente la aplicación web.

La carga de archivos está desactivada por defecto. Su activación local y limitaciones están en [docs/CARGA_LOCAL.md](docs/CARGA_LOCAL.md). Consultar también [SECURITY.md](SECURITY.md).

## Próximas mejoras

Históricos por fecha de corte, conciliación de compras en camino, recepción parcial real, métricas de servicio, pronósticos evaluados contra una referencia simple y pruebas de modelos con separación temporal. Antes de usar datos reales en un servidor: autenticación, permisos, límites de procesamiento, almacenamiento y políticas de retención.
