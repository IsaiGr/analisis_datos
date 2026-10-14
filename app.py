import os
from hashlib import sha256
from numbers import Number
from zipfile import BadZipFile

import pandas as pd
import streamlit as st

from src.data_pipeline import (
    enrich_forecast, add_forecast_context, load_demand, load_forecast, load_transits, validate_inputs,
    apply_filters, pending_demand, strict_sum, coverage_text,
    COVERAGE_PRIORITY_MONTHS, sort_by_coverage_priority,
)
from src.models import model_readiness, segment_inventory
from src.demo_data import DEMO_REFERENCE_DATE, make_demo_data
from src.dashboard_charts import (
    arrival_chart, capital_by_consumption_chart, catalog_link_chart, demand_heatmap,
    inventory_concentration_chart, logistics_status_chart, monthly_demand_chart,
    priority_purchase_chart, status_label, stock_consumption_chart, coverage_priority_chart,
)

st.set_page_config(page_title="Refacciones Analytics", page_icon="📦", layout="wide")

st.markdown("""
<style>
.block-container { padding-top: 1.4rem; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_demo():
    forecast, demand, transits = make_demo_data()
    forecast = enrich_forecast(forecast)
    enriched, engine = segment_inventory(forecast)
    return enriched, demand, transits, engine


def metric_value(df, col):
    return strict_sum(df[col]) if col in df else float("nan")


def business_context(problem: str, solution: str, decision: str):
    st.markdown(f"**Problema:** {problem}")
    st.markdown(f"**Qué resuelve:** {solution}")
    st.markdown(f"**Decisión que permite tomar:** {decision}")


def money(value: float) -> str:
    return "Sin dato completo" if pd.isna(value) else f"${value:,.0f} MXN"


def _number_text(value, decimals=0, suffix=""):
    if pd.isna(value):
        return "Sin dato"
    number = float(value)
    if decimals == 2 and abs(number - round(number)) < 0.005:
        decimals = 0
    if decimals == 1 and abs(number - round(number)) < 0.05:
        decimals = 0
    return f"{number:,.{decimals}f}{suffix}"


def display_table(frame: pd.DataFrame):
    """Format visible values without changing the numeric analysis tables."""
    out = frame.copy()
    # Provenance is displayed separately; do not send internal metadata to Arrow.
    out.attrs = {}
    for col in out.columns:
        label = str(col).lower()
        if "cobertura" in label and "meses" in label:
            out[col] = out[col].map(coverage_text)
        elif "mxn" in label:
            out[col] = out[col].map(lambda x: _number_text(x, 0, " MXN") if isinstance(x, Number) else x)
        elif "usd" in label:
            out[col] = out[col].map(lambda x: _number_text(x, 2, " USD") if isinstance(x, Number) else x)
        elif "meses" in label:
            out[col] = out[col].map(lambda x: _number_text(x, 1, " meses") if isinstance(x, Number) else x)
        elif "piezas" in label or "unidades" in label:
            out[col] = out[col].map(lambda x: _number_text(x, 2, " pzas") if isinstance(x, Number) else x)
        elif any(token in label for token in ["refacciones", "facturas", "ordenes", "órdenes", "líneas", "fila excel"]):
            out[col] = out[col].map(lambda x: _number_text(x, 0) if isinstance(x, Number) else x)
    return out.astype(object).where(out.notna(), "Sin dato")


def source_info(title: str, source_name: str, sheet: str, data_range: str, fields: str):
    with st.expander(f"Origen de la información · {title}", expanded=False):
        st.markdown(f"**Fuente:** `{source_name}`")
        st.markdown(f"**Hoja:** `{sheet}` · **Rango:** `{data_range}`")
        st.markdown(f"**Campos utilizados:** {fields}")
        st.caption("En la demostración, todos los registros y referencias a hojas/filas son ficticios y se generan en src/demo_data.py. En carga local, se conservan los valores guardados del Excel; la app no ejecuta sus fórmulas.")


def chart_rows(frame, fields):
    """Charts show known values only; never quietly count missing values as zero."""
    valid = frame[fields].notna().all(axis=1)
    if (~valid).any():
        st.caption(f"Gráfico parcial: excluye {int((~valid).sum()):,} registros sin datos válidos para esta comparación. No se consideran cero.")
    return frame.loc[valid]


def source_range(frame, last_column, header):
    last = int(frame["source_row"].max()) if len(frame) else header
    return f"A{header}:{last_column}{last}"


def show_chart(fig, key):
    st.plotly_chart(fig, width="stretch", key=key, config={"displaylogo": False})


st.title("Refacciones Analytics")
st.caption("Inventario · demanda · compras · tránsitos · calidad de datos")
uploads_enabled = os.environ.get("REFACCIONES_ENABLE_UPLOADS", "0") == "1"

with st.sidebar:
    st.header("Fuentes de datos")
    uploaded_forecast = uploaded_transit = uploaded_demand = None
    if uploads_enabled:
        st.warning("Carga local habilitada. Usar únicamente en un entorno privado y controlado.")
        uploaded_forecast = st.file_uploader("Forecast / inventario", type=["xlsx"], key="forecast", max_upload_size=25)
        uploaded_transit = st.file_uploader("Tránsitos / ingresos", type=["xlsx"], key="transits", max_upload_size=25)
        uploaded_demand = st.file_uploader("Órdenes de refacciones", type=["xlsx"], key="demand", max_upload_size=25)
    else:
        st.info("Portafolio público: datos 100 % ficticios. Carga de archivos privados desactivada.")
    st.divider()
    st.caption("La demostración no busca ni lee archivos del equipo. Los ejemplos se generan en memoria.")
    if st.button("Actualizar información", width="stretch"):
        load_demo.clear()
        st.session_state.pop("private_sources", None)
        st.rerun()

def load_uploaded_sources(forecast_bytes, transit_bytes, demand_bytes):
    forecast = enrich_forecast(load_forecast(forecast_bytes))
    enriched, engine = segment_inventory(forecast)
    return enriched, load_demand(demand_bytes), load_transits(transit_bytes), engine


if uploaded_forecast or uploaded_transit or uploaded_demand:
    if not all([uploaded_forecast, uploaded_transit, uploaded_demand]):
        st.warning("Carga los tres libros para evitar mezclar periodos o fuentes diferentes.")
        st.stop()
    buffers = (uploaded_forecast.getvalue(), uploaded_transit.getvalue(), uploaded_demand.getvalue())
    signature = tuple(sha256(buffer).hexdigest() for buffer in buffers)
    try:
        cached = st.session_state.get("private_sources")
        if cached is None or cached[0] != signature:
            cached = (signature, load_uploaded_sources(*buffers))
            st.session_state["private_sources"] = cached
        forecast, demand, transits, engine = cached[1]
    except (ValueError, OSError, KeyError, BadZipFile):
        st.error("No se pudo leer la estructura de los libros. Revisa las hojas, columnas y formato XLSX indicados en la documentación.")
        st.stop()
    source_update_label = "Carga manual realizada en esta sesión"
    source_names = {"forecast": uploaded_forecast.name, "transits": uploaded_transit.name, "demand": uploaded_demand.name}
    source_updates = [{"Archivo": name, "Modificación del archivo": "Carga en sesión; corte de negocio por confirmar"} for name in source_names.values()]
else:
    st.session_state.pop("private_sources", None)
    forecast, demand, transits, engine = load_demo()
    source_update_label = "Demostración ficticia reproducible, sin conexión a sistemas reales"
    source_names = {"forecast": "Inventario ficticio", "transits": "Tránsitos ficticios", "demand": "Órdenes ficticias"}
    source_updates = [{"Archivo": name, "Modificación del archivo": "No aplica: ejemplo generado en memoria"} for name in source_names.values()]

is_demo = not (uploaded_forecast or uploaded_transit or uploaded_demand)
st.info("DEMO · Todos los códigos, cantidades, importes, proveedores y fechas son inventados." if is_demo else "DATOS LOCALES · No compartas capturas, descargas ni acceso a esta sesión sin autorización.")

# Relación común por código de refacción para que los filtros sean globales.
demand = add_forecast_context(demand, forecast)
transits = add_forecast_context(transits, forecast)

validation = validate_inputs(forecast, demand, transits)

st.sidebar.divider()
st.sidebar.subheader("Estado de la información")
st.sidebar.caption(source_update_label)
st.sidebar.caption("La demo no representa una empresa real. Las cargas locales, si se habilitan, se conservan solo en la memoria de esta sesión y no se escriben en disco ni en la caché global. No hay conexión de negocio en tiempo real.")
operational_forecast = forecast.loc[forecast["catalog_eligible"]].copy()
filter_options = {}
for col in ["family", "origin", "category", "priority", "abc_class"]:
    values = set()
    for frame in [operational_forecast, demand, transits]:
        if col in frame:
            values.update(frame[col].fillna("Sin relación / sin dato").astype(str))
    filter_options[col] = sorted(values)
with st.sidebar:
    st.header("Filtros")
    selections = {col: st.multiselect(label, filter_options[col], default=filter_options[col]) for col, label in [
        ("family", "Familia"), ("origin", "Origen"), ("category", "Categoría"), ("priority", "Prioridad del Excel"), ("abc_class", "Clase ABC")
    ]}
    st.caption("ABC se conserva como etiqueta de la fuente; en la demo es ficticia. La app no calcula una clasificación 80/15/5 por valor.")
    only_risk = st.checkbox("Solo faltante bruto estimado")
    only_low_coverage = st.checkbox(f"Solo cobertura menor a {COVERAGE_PRIORITY_MONTHS:g} meses", key="only_low_coverage")
    st.caption(f"Atender primero: cobertura menor a {COVERAGE_PRIORITY_MONTHS:g} meses. Este filtro también selecciona sus pedidos y tránsitos por código; sin relación única no se puede asignar cobertura.")

def apply_global_filters(frame: pd.DataFrame) -> pd.DataFrame:
    risk_items = forecast.loc[forecast["shortage_gap"] > 0, "item"] if only_risk else None
    coverage_items = forecast.loc[forecast["coverage_priority"].fillna(False), "item"] if only_low_coverage else None
    return apply_filters(frame, selections, filter_options, risk_items, coverage_items)


filtered = apply_global_filters(operational_forecast)
demand_filtered = apply_global_filters(demand)
transits_filtered = apply_global_filters(transits)
coverage_priority_rows = filtered.loc[filtered["coverage_priority"].fillna(False)]
coverage_unknown = filtered.loc[~filtered["coverage_calculable"]]
coverage_zero_demand = int(coverage_unknown["coverage_status"].eq("Sin consumo registrado").sum())
st.caption("Los gráficos y tablas de operación usan los filtros de la barra lateral. Pasa el cursor para ver cantidades y unidades; pulsa una leyenda para ocultar o mostrar una serie.")
st.sidebar.caption("Todas las opciones = sin restricción, incluidos registros sin relación con el catálogo. Sin opciones = sin resultados. La revisión de calidad siempre considera los archivos completos.")
excluded = forecast.loc[~forecast["catalog_eligible"]]
if not excluded.empty:
    st.warning(f"Inventario y propuestas de compra: se excluyen {len(excluded):,} filas sin código único ({excluded['item'].nunique():,} códigos repetidos). Los registros originales se conservan en Calidad y modelos. Los totales no representan todo el archivo.")
not_calculable = int((~filtered["risk_calculable"]).sum())
if not_calculable:
    st.warning(f"En la selección hay {not_calculable:,} refacciones sin datos suficientes para estimar faltantes. No se consideran sin riesgo.")

tab_overview, tab_inventory, tab_demand, tab_logistics, tab_quality = st.tabs([
    "Resumen ejecutivo", "Inventario y compras", "Demanda", "Logística", "Calidad y modelos"
])

with tab_overview:
    st.subheader("Resumen para decidir")
    business_context(
        "La información de inventario, compras, demanda y logística está separada en distintos libros y es difícil saber qué atender primero.",
        f"Da prioridad a las refacciones con menos de {COVERAGE_PRIORITY_MONTHS:g} meses de cobertura y muestra su impacto económico y faltante estimado.",
        "Atender primero las piezas con menor cobertura y confirmar sus pedidos en camino antes de comprar."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Refacciones con código único", f"{filtered['item'].nunique():,} códigos")
    c2.metric("Valor del inventario seleccionado", money(metric_value(filtered, 'inventory_value')))
    c3.metric("Propuesta de compra del Excel", money(metric_value(filtered, 'purchase_amount')))
    c4, c5, c6 = st.columns(3)
    c4.metric(f"Prioritarias por cobertura (<{COVERAGE_PRIORITY_MONTHS:g} meses)", f"{coverage_priority_rows['item'].nunique():,} códigos")
    c5.metric("Con faltante bruto estimado", f"{filtered.loc[filtered['shortage_gap'] > 0, 'item'].nunique():,} códigos")
    pending = pending_demand(demand_filtered)
    c6.metric("Pedidos con estado Back Order", _number_text(pending['quantity'], 2, " piezas"))
    st.info(f"Regla de atención: cobertura = existencias actuales ÷ demanda mensual ajustada. Menos de {COVERAGE_PRIORITY_MONTHS:g} meses tiene prioridad; {COVERAGE_PRIORITY_MONTHS:g} meses exactos no activa esta regla. No incluye compras en camino ni sustituye la prioridad del Excel o el faltante por tiempo de entrega.")
    if len(coverage_unknown):
        st.caption(f"Cobertura no calculable en {len(coverage_unknown):,} refacciones de la selección: {coverage_zero_demand:,} sin consumo registrado y {len(coverage_unknown) - coverage_zero_demand:,} con datos insuficientes. Se muestran por separado; no son cobertura cero ni se consideran protegidas.")
    st.caption(f"Back Order: suma de cantidades en {pending['rows']:,} líneas de Free Sales con ese estado, después de los filtros; es el estado guardado en el archivo, no un saldo en tiempo real. No usa el promedio de Back Order de 3 meses del forecast.")
    if pending["unknown_status"]:
        st.warning(f"{pending['unknown_status']:,} líneas no tienen estado: el saldo pendiente completo no puede confirmarse.")
    st.info("El faltante bruto compara existencias con demanda mensual ajustada × meses de entrega. No descuenta pedidos en camino ni calcula una orden de compra. La propuesta del Excel requiere validación operativa; ‘Sin dato’ no significa cero.")
    source_info("inventario y propuestas", source_names["forecast"], "1. FORECAST", source_range(forecast, "BT", 4), "inventario, demanda mensual ajustada guardada, propuesta de compra, prioridad y ABC")
    source_info("pedidos pendientes", source_names["demand"], "Free Sales", source_range(demand, "T", 2), "Quantity de líneas cuyo User Status es Back Order; no incluye Canceled ni APPROVED")
    st.subheader("20 refacciones para atender primero")
    st.caption(f"Primero las que tienen menos de {COVERAGE_PRIORITY_MONTHS:g} meses, de menor a mayor cobertura. En empate: mayor faltante bruto y después mayor importe del Excel. Los casos no calculables quedan al final; esta lista no autoriza compras.")
    cols = [c for c in ["item", "coverage_months_calc", "coverage_status", "description", "family", "origin", "inventory", "monthly_demand", "on_order", "shortage_gap", "priority", "recommended_qty", "purchase_amount", "purchase_review", "source_row"] if c in filtered]
    top_actions = sort_by_coverage_priority(filtered)[cols].head(20).rename(columns={"item": "Código", "coverage_months_calc": "Cobertura (meses)", "coverage_status": "Atención por cobertura", "description": "Descripción", "family": "Familia", "origin": "Origen", "priority": "Prioridad del Excel", "inventory": "Inventario (piezas)", "monthly_demand": "Demanda mensual ajustada (piezas)", "on_order": "Compras en camino (piezas)", "shortage_gap": "Faltante bruto (piezas)", "recommended_qty": "Propuesta Excel (piezas)", "purchase_amount": "Propuesta Excel (MXN)", "purchase_review": "Validación pendiente", "source_row": "Fila Excel"})
    st.dataframe(display_table(top_actions), width="stretch", hide_index=True)
    priority = filtered.groupby("priority", dropna=False).agg(SKUs=("item", "nunique"), Compra=("purchase_amount", strict_sum), Inventario=("inventory_value", strict_sum)).reset_index().sort_values("Compra", ascending=False)
    priority = priority.rename(columns={"priority": "Prioridad del Excel", "SKUs": "Refacciones", "Compra": "Propuesta Excel (MXN)", "Inventario": "Valor inventario (MXN)"})
    if filtered.empty:
        st.info("No hay refacciones con esta combinación de filtros. Amplía la selección para ver los gráficos.")
    else:
        chart_left, chart_right = st.columns(2)
        with chart_left:
            st.markdown("**¿Qué prioridad del Excel concentra el presupuesto propuesto?**")
            show_chart(priority_purchase_chart(chart_rows(filtered, ["purchase_amount"])), "overview_priority")
            st.caption("Importes guardados en el Excel, por prioridad. No constituyen compras autorizadas ni se recalculan al cargar órdenes nuevas.")
        with chart_right:
            st.markdown("**¿Dónde se concentra el dinero en inventario?**")
            show_chart(inventory_concentration_chart(chart_rows(filtered, ["inventory_value"])), "overview_concentration")
            st.caption("Las columnas muestran pesos por familia. La línea suma su participación en el valor total de la selección; no recalcula la clase ABC.")
    st.markdown("**Detalle por prioridad del Excel**")
    st.dataframe(display_table(priority), width="stretch", hide_index=True)

with tab_inventory:
    st.subheader("¿Dónde puede faltar inventario o sobrar capital?")
    business_context(
        "Comprar tarde puede detener reparaciones o producción; comprar de más inmoviliza dinero y aumenta el riesgo de obsolescencia.",
        f"Prioriza coberturas menores a {COVERAGE_PRIORITY_MONTHS:g} meses y compara existencias, demanda ajustada y meses de entrega.",
        "Revisar pedidos en camino, compromisos y fechas antes de decidir si comprar."
    )
    source_info("riesgo de inventario", source_names["forecast"], "1. FORECAST", source_range(forecast, "BT", 4), "inventario actual, demanda mensual ajustada, tiempo de entrega en meses, propuesta y salud del inventario")
    with st.expander("Cómo se calcula la cobertura, el faltante y qué falta confirmar"):
        st.markdown(f"**Cobertura = inventario actual ÷ demanda mensual ajustada. Prioridad si el resultado es menor a {COVERAGE_PRIORITY_MONTHS:g} meses, sin redondear para clasificar.** Por ejemplo, 30 piezas ÷ 10 piezas/mes = 3 meses: atender primero. No suma compras en camino.")
        st.markdown("**Faltante bruto = máximo de 0 y (demanda mensual ajustada × meses de entrega − inventario actual).** Ejemplo: 10 piezas/mes × 5 meses − 20 piezas disponibles = 30 piezas de faltante bruto.")
        st.write("La demanda mensual es un dato de entrada: ficticio en la demo y guardado en el archivo en modo local. No es un pronóstico entrenado por la app.")
        st.write("Antes de comprar faltan por conciliar cantidades y fechas de pedidos en camino, piezas comprometidas, existencias de seguridad y alternos. No se suman las compras en camino del forecast y los tránsitos: podrían ser el mismo pedido.")
    st.markdown(f"**¿Qué refacciones están por debajo de {COVERAGE_PRIORITY_MONTHS:g} meses de cobertura?**")
    inventory_limit = st.select_slider("Refacciones con menor cobertura a mostrar", options=[10, 15, 20], value=15)
    if filtered["coverage_calculable"].any():
        show_chart(coverage_priority_chart(filtered, inventory_limit), "inventory_coverage_priority")
        st.caption(f"Rojo: atender primero, menos de {COVERAGE_PRIORITY_MONTHS:g} meses. Azul: {COVERAGE_PRIORITY_MONTHS:g} meses o más, sin concluir que no existe otro riesgo. La línea marca el umbral; los puntos en cero representan existencias agotadas con demanda positiva. Los casos no calculables no se grafican.")
    else:
        st.info("No hay refacciones con cobertura calculable en esta selección. Sin consumo o sin datos válidos no se asigna cobertura cero.")
    st.markdown("**Refacciones prioritarias por cobertura**")
    coverage_table = sort_by_coverage_priority(coverage_priority_rows)[["item", "coverage_months_calc", "coverage_status", "description", "family", "inventory", "monthly_demand", "on_order", "shortage_gap", "priority", "source_row"]].head(50).rename(columns={"item": "Código", "coverage_months_calc": "Cobertura (meses)", "coverage_status": "Atención por cobertura", "description": "Descripción", "family": "Familia", "inventory": "Inventario (piezas)", "monthly_demand": "Demanda mensual ajustada (piezas)", "on_order": "Compras en camino (piezas)", "shortage_gap": "Faltante bruto (piezas)", "priority": "Prioridad del Excel", "source_row": "Fila Excel"})
    st.dataframe(display_table(coverage_table), width="stretch", hide_index=True)
    st.caption(f"Se muestran las primeras {len(coverage_table):,} de {len(coverage_priority_rows):,} refacciones prioritarias filtradas. {len(coverage_unknown):,} refacciones no tienen cobertura calculable ({coverage_zero_demand:,} sin consumo registrado); no se interpretan como cero ni como cobertura suficiente.")
    st.markdown("**¿Las existencias alcanzan para el consumo de un mes?**")
    if (filtered["monthly_demand"] > 0).any():
        show_chart(stock_consumption_chart(chart_rows(filtered, ["inventory", "monthly_demand"]), inventory_limit), "inventory_stock")
        st.caption("Círculo azul: existencias. Rombo ámbar: demanda mensual ajustada del Excel. Si el círculo queda a la izquierda, el inventario no cubre ese mes estimado. No incluye compras en camino ni tiempos de entrega.")
    else:
        st.info("No hay refacciones con consumo mensual positivo en esta selección.")
    st.markdown("**¿Cuánto dinero está en piezas con poco o ningún consumo?**")
    if (filtered["inventory"] > 0).any():
        show_chart(capital_by_consumption_chart(chart_rows(filtered, ["inventory", "monthly_demand", "inventory_value"])), "inventory_capital")
        st.caption(f"Los dos primeros rangos tienen menos de {COVERAGE_PRIORITY_MONTHS:g} meses y requieren atención prioritaria. {COVERAGE_PRIORITY_MONTHS:g} meses o más no significa automáticamente exceso. Sin consumo registrado no demuestra obsolescencia. Solo se distribuye capital de existencias positivas.")
    else:
        st.info("No hay existencias positivas para distribuir por cobertura.")
    left, right = st.columns([1.4, 1])
    with left:
        st.markdown("**Grupos de comportamiento de las refacciones**")
        seg = filtered.groupby("segment", dropna=False).agg(SKUs=("item", "nunique"), Inventario=("inventory_value", strict_sum), Demanda=("monthly_demand", strict_sum), Compra=("purchase_amount", strict_sum)).reset_index()
        seg = seg.rename(columns={"segment": "Grupo", "SKUs": "Refacciones", "Inventario": "Valor inventario (MXN)", "Demanda": "Demanda mensual ajustada (piezas)", "Compra": "Propuesta Excel (MXN)"})
        st.dataframe(display_table(seg.sort_values("Propuesta Excel (MXN)", ascending=False)), width="stretch", hide_index=True)
        st.caption("Grupos exploratorios, no categorías de compra. Los registros incompletos no se rellenan con ceros para evaluarlos; ‘No evaluado’ no significa comportamiento normal.")
    with right:
        st.markdown("**Indicadores de decisión**")
        for label, value in [
            (f"Prioritarias por cobertura (<{COVERAGE_PRIORITY_MONTHS:g} meses)", int(coverage_priority_rows['item'].nunique())),
            ("Con faltante bruto estimado", int((filtered["shortage_gap"] > 0).sum())),
            ("Sin movimiento o lentas", int(filtered["inventory_health"].astype(str).str.contains("Sin|Lento|Obsoleto", case=False, na=False).sum())),
            ("Componentes críticos", int(filtered["key_component"].astype(str).str.lower().isin(["si", "sí", "yes", "true"]).sum())),
            ("Casos fuera de patrón", int(filtered["anomaly"].sum())),
        ]:
            st.metric(label, f"{value:,}")
    st.markdown("**Refacciones con faltante bruto, atendiendo primero la menor cobertura**")
    risk_table = sort_by_coverage_priority(filtered.loc[filtered['shortage_gap'].gt(0)])[[c for c in ["item", "coverage_months_calc", "coverage_status", "description", "family", "lead_time", "monthly_demand", "inventory", "shortage_gap", "on_order", "priority", "risk_note", "source_row"] if c in filtered]].head(50).rename(columns={"item": "Código", "coverage_months_calc": "Cobertura (meses)", "coverage_status": "Atención por cobertura", "description": "Descripción", "family": "Familia", "lead_time": "Tiempo de entrega (meses)", "monthly_demand": "Demanda mensual ajustada (piezas)", "inventory": "Inventario (piezas)", "shortage_gap": "Faltante bruto (piezas)", "on_order": "Compras en camino del Excel (piezas)", "priority": "Prioridad del Excel", "risk_note": "Antes de decidir", "source_row": "Fila Excel"})
    st.dataframe(display_table(risk_table), width="stretch", hide_index=True)

with tab_demand:
    st.subheader("¿Qué se está solicitando y qué no se ha podido atender?")
    business_context(
        "Los pedidos pendientes pueden perderse entre miles de órdenes. Una cancelación requiere investigar su causa; no demuestra por sí sola falta de inventario.",
        "Agrupa las solicitudes por mes, pieza, modelo y estado para encontrar los focos de servicio.",
        "Atacar las piezas que más afectan al cliente y ajustar las compras futuras a la demanda real."
    )
    source_info("demanda y back orders", source_names["demand"], "Free Sales", source_range(demand, "T", 2), "fecha de solicitud, pieza, modelo, cantidad y estado de la orden")
    demand_link_rate = demand["catalog_match"].eq("Relación única").mean() if len(demand) else 0
    st.caption(f"Relación única con el catálogo: {demand_link_rate:.1%} del archivo. Un código repetido no hereda familia, prioridad ni ABC. Los filtros usan únicamente atributos conocidos.")
    demand_rows = demand_filtered.assign(status=demand_filtered["status"].map(status_label))
    status = demand_rows.groupby("status", dropna=False).agg(Lineas=("item", "size"), Unidades=("quantity", strict_sum)).reset_index().sort_values("Unidades", ascending=False).rename(columns={"status": "Estado de la orden", "Lineas": "Líneas de orden", "Unidades": "Unidades solicitadas"})
    if "posting_date" in demand_filtered:
        st.markdown("**¿Cómo cambia la demanda y el estado de sus órdenes cada mes?**")
        demand_view = st.radio("Comparar demanda por", ["Piezas solicitadas", "Porcentaje de cada mes"], horizontal=True)
        dated_demand = demand_filtered.dropna(subset=["posting_date"])
        if dated_demand.empty:
            st.info("No hay solicitudes con fecha válida para graficar esta selección.")
        else:
            demand_plot = chart_rows(demand_filtered, ["quantity"])
            show_chart(monthly_demand_chart(demand_plot, demand_view == "Porcentaje de cada mes"), "demand_monthly")
            start, end = dated_demand["posting_date"].min(), dated_demand["posting_date"].max()
            st.caption(f"Solicitudes fechadas del {start:%d/%m/%Y} al {end:%d/%m/%Y}. El primer y último mes pueden estar incompletos. El color representa el estado que figura hoy en el archivo, no su evolución histórica. Aprobado no equivale a entregado.")
            missing_dates = int(demand_filtered["posting_date"].isna().sum())
            if missing_dates:
                st.caption(f"{missing_dates:,} registros sin fecha válida permanecen en las tablas, pero se excluyen de los gráficos mensuales.")
            st.markdown("**¿Qué refacciones concentran las solicitudes y en qué meses?**")
            demand_limit = st.select_slider("Refacciones más solicitadas a mostrar", options=[10, 15, 20], value=15)
            show_chart(demand_heatmap(chart_rows(demand_plot, ["item"]), demand_limit), "demand_heatmap")
            st.caption("Un tono más oscuro indica más piezas solicitadas. Pasa el cursor para ver el código, la descripción y la cantidad exacta. Un mes sin registros queda vacío: no se interpreta como demanda cero.")
    st.markdown("**Detalle por estado de orden**")
    st.dataframe(display_table(status), width="stretch", hide_index=True)
    demand_detail = demand_filtered.groupby([c for c in ["item", "description", "customer_model"] if c in demand_filtered], dropna=False).agg(Unidades=("quantity", strict_sum), Ordenes=("sales_order", "nunique"), Lineas=("item", "size")).reset_index().sort_values("Unidades", ascending=False).head(50).rename(columns={"item": "Código", "description": "Descripción", "customer_model": "Modelo", "Unidades": "Unidades solicitadas", "Ordenes": "Órdenes", "Lineas": "Líneas de orden"})
    st.dataframe(display_table(demand_detail), width="stretch", hide_index=True)

with tab_logistics:
    st.subheader("¿Qué ingresos necesitan seguimiento?")
    business_context(
        "Una orden puede estar registrada, pero no disponible para producción o servicio si permanece en tránsito o sin fecha de llegada.",
        "Compara los estados reportados por origen y señala fechas de llegada vencidas o sin confirmar.",
        "Dar seguimiento a órdenes vencidas, escalar retrasos y confirmar fechas de recepción."
    )
    transit_sheet = "INBOUND" if "item" in transits else "DASHBOARD"
    source_info("seguimiento logístico", source_names["transits"], transit_sheet, source_range(transits, "P", 1 if transit_sheet == "INBOUND" else 5), "pieza, factura, cantidad, precio unitario, fábrica, ETA y estado; o resumen heredado cuando no hay INBOUND")
    transit_link_rate = transits["catalog_match"].eq("Relación única").mean() if "catalog_match" in transits and len(transits) else 0
    st.caption(f"Relación única con el catálogo: {transit_link_rate:.1%} del archivo. Se conserva el origen y categoría del detalle logístico; un código repetido no hereda prioridad ni ABC.")
    if "quantity" in transits_filtered:
        logistics_rows = transits_filtered.copy()
        completed = logistics_rows["status"].astype(str).str.strip().str.casefold().eq("completed")
        logistics_rows["received_units"] = logistics_rows["quantity"].where(completed, 0)
        logistics_rows["unreceived_units"] = logistics_rows["quantity"].where(~completed, 0)
        transit_summary = logistics_rows.groupby("status", dropna=False).agg(invoice_count=("invoice", "nunique"), invoice_amount_usd=("invoice_amount_usd", strict_sum), planned_units=("quantity", strict_sum), received_units=("received_units", strict_sum), pending_invoices=("invoice", "nunique"), unreceived_units=("unreceived_units", strict_sum)).reset_index()
        transit_summary.loc[transit_summary["status"].astype(str).str.casefold().eq("completed"), "pending_invoices"] = 0
        if logistics_rows.empty:
            st.info("No hay registros logísticos con esta combinación de filtros.")
        else:
            st.markdown("**¿En qué estado están las piezas de cada origen?**")
            logistics_view = st.radio("Comparar logística por", ["Piezas registradas", "Porcentaje de cada origen"], horizontal=True)
            logistics_plot = chart_rows(logistics_rows, ["quantity"])
            show_chart(logistics_status_chart(logistics_plot, logistics_view == "Porcentaje de cada origen"), "logistics_status")
            st.caption("Cada franja representa piezas registradas bajo un estado. Un ingreso parcial no informa cuántas llegaron; estas cantidades no equivalen a piezas pendientes exactas.")
            if "eta" in logistics_rows:
                st.markdown("**¿Qué fechas de llegada requieren revisión?**")
                reference_date = st.date_input("Fecha para revisar vencimientos", value=DEMO_REFERENCE_DATE if is_demo else pd.Timestamp.now(tz="America/Mexico_City").date())
                show_chart(arrival_chart(logistics_plot, reference_date), "logistics_arrivals")
                st.caption(f"Revisión al {reference_date:%d/%m/%Y}, solo para registros cuyo estado no es Completado. Una fecha vencida puede indicar retraso o información sin actualizar: confirma con logística. Las facturas pueden aparecer en más de un grupo.")
    else:
        transit_summary = transits_filtered.copy()
        st.info("Este libro contiene un resumen sin detalle por refacción. Para graficar por origen y fecha de llegada se necesita la hoja INBOUND.")
    transit_summary["status"] = transit_summary["status"].map(status_label)
    transit_view = transit_summary.rename(columns={"status": "Estado", "invoice_count": "Facturas", "invoice_amount_usd": "Monto factura (USD)", "planned_units": "Piezas planeadas", "received_units": "Piezas en registros completados" if "quantity" in transits_filtered else "Piezas recibidas", "pending_invoices": "Facturas pendientes", "unreceived_units": "Piezas en registros sin completar" if "quantity" in transits_filtered else "Piezas no recibidas", "total_pending": "Total pendiente (facturas)"})
    st.markdown("**Detalle por estado logístico**")
    st.dataframe(display_table(transit_view), width="stretch", hide_index=True)
    st.caption("La vista logística se calcula desde el detalle INBOUND y se filtra por pieza, familia, categoría, origen, prioridad y clase ABC cuando existe relación con el catálogo.")

with tab_quality:
    st.subheader("¿Qué tan confiable es la información?")
    business_context(
        "Los errores, duplicados y diferencias entre reportes pueden generar compras incorrectas o esconder faltantes.",
        "Revisa la calidad de las fuentes antes de usar un indicador para tomar una decisión.",
        "Corregir la fuente, pedir validación al responsable o excluir temporalmente un dato afectado."
    )
    source_info("validación de datos", f"{source_names['forecast']} · {source_names['demand']} · {source_names['transits']}", "Varias hojas", "Rangos procesados por la aplicación", "existencia de fuentes, columnas críticas, duplicados y errores visibles")
    st.info("Esta sección revisa los archivos completos. No cambia con los filtros operativos, para que los problemas de las fuentes permanezcan visibles.")
    st.markdown("**¿Cuántos registros podemos relacionar con el catálogo?**")
    show_chart(catalog_link_chart(forecast, demand, transits), "quality_catalog")
    st.caption("Un código repetido se muestra aparte: no se elige una fila del catálogo para asignar atributos. Los registros sin relación única permanecen en demanda y logística, pero un filtro por atributos desconocidos puede excluirlos.")
    q = pd.DataFrame(validation["checks"])
    quality_ok, quality_review = st.columns(2)
    quality_ok.metric("Comprobaciones sin alerta", f"{int(q['status'].eq('OK').sum())} de {len(q)}")
    quality_review.metric("Comprobaciones por revisar", f"{int(q['status'].eq('REVISAR').sum())} de {len(q)}")
    st.dataframe(q.rename(columns={"check": "Comprobación", "status": "Resultado", "detail": "Detalle"}), width="stretch", hide_index=True)
    with st.expander("Archivos utilizados y alcance de la actualización", expanded=False):
        st.dataframe(pd.DataFrame(source_updates), hide_index=True, width="stretch")
        st.caption("La demo es reproducible y ficticia. En modo local se procesan las tres cargas de la sesión, sin historial ni lectura automática de archivos del equipo.")
    with st.expander("Registros de inventario que requieren revisión", expanded=False):
        review = forecast.loc[~forecast['risk_calculable'] | forecast['purchase_amount_consistent'].ne(True).fillna(True)]
        review = review[["item", "family", "origin", "abc_class", "inventory", "monthly_demand", "lead_time", "risk_note", "purchase_review", "source_row"]].rename(columns={"item": "Código", "family": "Familia", "origin": "Origen", "abc_class": "ABC del Excel", "inventory": "Inventario (piezas)", "monthly_demand": "Demanda mensual ajustada (piezas)", "lead_time": "Entrega (meses)", "risk_note": "Revisión de faltante", "purchase_review": "Revisión de compra", "source_row": "Fila Excel"})
        st.caption(f"{len(review):,} filas. Se conservan todas las apariciones de cada código repetido; no se suman ni se eliminan de la fuente.")
        st.dataframe(display_table(review), hide_index=True, width="stretch")
    with st.expander("Incidencias con hoja, fila y valor original", expanded=False):
        issues = validation['issues'].copy()
        issues['source'] = issues['source'].map(source_names)
        issue_view = issues.rename(columns={"source": "Archivo", "sheet": "Hoja", "row": "Fila Excel", "column": "Columna", "raw": "Valor original", "issue": "Qué revisar"})
        st.caption(f"{len(issue_view):,} incidencias (una celda puede tener más de una). Vista de las primeras 500; descarga el detalle completo para corregir la fuente.")
        st.dataframe(display_table(issue_view.head(500)), hide_index=True, width="stretch")
        # Escape formula-like text in CSV exports; original workbook cells are untouched.
        export = issue_view.map(lambda value: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value)
        st.download_button("Descargar incidencias", export.to_csv(index=False).encode('utf-8-sig'), file_name="incidencias_datos.csv", mime="text/csv")
    with st.expander("Detalle técnico de los modelos", expanded=False):
        st.markdown(f"**Motor analítico utilizado:** {engine}")
        st.dataframe(pd.DataFrame(model_readiness(forecast)), width="stretch", hide_index=True)
        st.warning("Random Forest, Keras/PyTorch y SARSA se incorporarán cuando existan históricos de varios cortes, una variable objetivo validada y un simulador de costos. Esto evita producir recomendaciones difíciles de justificar.")
