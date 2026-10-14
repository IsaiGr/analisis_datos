# Carga local opcional

La demo funciona sin archivos. Conservar esta configuración para portafolio público.

En un equipo privado, únicamente con libros propios y de confianza, puede habilitarse la carga para esa ejecución:

```powershell
$env:REFACCIONES_ENABLE_UPLOADS = "1"
python -m streamlit run app.py --server.address 127.0.0.1
```

Para volver al modo demo, detener el servidor, eliminar esa variable de la sesión y reiniciarlo. Se requieren tres cargas para no mezclar fuentes. Límite por archivo: 25 MB. No hay guardado automático, historial ni actualización desde una carpeta compartida.

Los adaptadores esperan una estructura específica, no cualquier libro de Excel:

| Fuente | Hoja | Encabezado | Datos principales |
| --- | --- | --- | --- |
| Inventario | `1. FORECAST` | Fila 4 | Item, existencias, demanda mensual, meses de entrega, costo MXN, propuesta y etiquetas |
| Órdenes | `Free Sales` | Fila 2 | Parts ID, User Status, Quantity, Posting Date, Sales Order |
| Tránsitos | `INBOUND` | Fila 1 | PART. NO., QTY, UNIT PRICE (USD), FACTORY, ETA, STATUS, INVOICE NO. |

Los nombres exactos, incluidos saltos de línea de algunos encabezados, están definidos en `load_forecast`, `load_demand` y `load_transits` en [src/data_pipeline.py](../src/data_pipeline.py). El adaptador de tránsitos conserva un respaldo para un resumen `DASHBOARD`, sin detalle por pieza; ese resumen no permite todos los cruces.

Las celdas con fórmulas requieren valores ya calculados y guardados por el programa de origen: esta aplicación no recalcula libros. Costos de inventario en MXN; precios y facturas logísticas en USD; existencias y demanda en piezas; tiempo de entrega y cobertura en meses. No se mezclan las monedas.

Antes de compartir esta sesión o sus descargas, obtener autorización sobre los datos. Este modo no está preparado para recibir archivos de desconocidos en internet; revisar [SECURITY.md](../SECURITY.md).
