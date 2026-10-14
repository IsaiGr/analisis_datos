"""Business charts built from the same filtered rows as the dashboard tables."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from src.data_pipeline import (
    COVERAGE_PRIORITY_MONTHS, add_coverage_indicators, catalog_matches,
    coverage_text, sort_by_coverage_priority,
)


BLUE = "#2563A6"
TEAL = "#087F8C"
AMBER = "#B76E00"
RED = "#C24145"
GRAY = "#758396"
STATUS_LABELS = {
    "approved": "Aprobado",
    "completed": "Completado", "in transit": "En tránsito",
    "pending dispatch": "Por despachar", "partial inbound": "Ingreso parcial",
    "collect": "Por recolectar", "not received": "No recibido",
    "partial delivered": "Entrega parcial", "pending inbound": "Por ingresar",
    "validate": "Por validar", "back order": "Pedido pendiente",
    "backorder": "Pedido pendiente", "cancelled": "Cancelado",
    "canceled": "Cancelado", "delivered": "Entregado", "open": "Abierto",
}
PALETTE = [BLUE, AMBER, TEAL, RED, "#7559A6", GRAY, "#B75D20", "#407B56"]
STATUS_COLORS = {
    "Completado": TEAL, "Entregado": TEAL, "Aprobado": TEAL,
    "En tránsito": BLUE, "Por ingresar": AMBER, "Pedido pendiente": AMBER,
    "Ingreso parcial": "#7559A6", "Entrega parcial": "#7559A6",
    "Cancelado": RED, "No recibido": RED, "Por validar": GRAY, "Sin estado": GRAY,
}
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def status_label(value):
    if pd.isna(value) or str(value).strip().lower() in {"", "nan", "none"}:
        return "Sin estado"
    return STATUS_LABELS.get(str(value).strip().lower(), str(value).strip())


def style_chart(fig, height=410):
    # Keep the tooltip's foreground and background together: Streamlit can
    # otherwise supply light text from its dark theme over a white tooltip.
    hover_style = dict(
        bgcolor="#F8FAFC", bordercolor="#64748B",
        font=dict(family="Arial, sans-serif", size=13, color="#102A43"),
    )
    fig.update_layout(
        template="plotly_white", height=height,
        font=dict(family="Arial, sans-serif", size=13),
        margin=dict(l=12, r=24, t=25, b=30),
        legend=dict(title_text="", orientation="h", y=-0.22, x=0),
        hoverlabel=hover_style,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        separators=".,",
    )
    fig.update_traces(hoverlabel=hover_style)
    fig.update_xaxes(automargin=True, zeroline=False)
    fig.update_yaxes(automargin=True, zeroline=False)
    return fig


def priority_purchase_chart(frame):
    frame = frame.dropna(subset=["purchase_amount"])
    totals = frame.assign(priority=frame["priority"].fillna("Sin prioridad")).groupby("priority")["purchase_amount"].sum().sort_values()
    fig = go.Figure()
    for label, value in totals.items():
        fig.add_shape(type="line", x0=0, x1=value, y0=label, y1=label,
                      line=dict(color="#C7D7E7", width=4))
    fig.add_trace(go.Scatter(
        x=totals.values, y=totals.index, mode="markers+text",
        marker=dict(size=13, color=BLUE),
        text=[f"${value:,.0f} MXN" for value in totals], textposition="middle right",
        cliponaxis=False, hovertemplate="%{y}<br>Propuesta del Excel: $%{x:,.2~f} MXN<extra></extra>",
    ))
    fig.update_layout(showlegend=False)
    fig.update_xaxes(title="Propuesta del Excel (MXN)", tickprefix="$", tickformat=",.0f", rangemode="tozero",
                     range=[min(0, totals.min() * 1.1) if len(totals) else 0, max(1, totals.max() * 1.55) if len(totals) else 1])
    fig.update_yaxes(type="category", categoryorder="array", categoryarray=totals.index.tolist(), showgrid=False)
    return style_chart(fig)


def inventory_concentration_chart(frame):
    frame = frame.dropna(subset=["inventory_value"])
    totals = frame.assign(family=frame["family"].fillna("Sin familia")).groupby("family")["inventory_value"].sum().sort_values(ascending=False)
    if len(totals) > 10:
        totals = pd.concat([totals.iloc[:10], pd.Series({"Otras familias": totals.iloc[10:].sum()})])
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=totals.index, y=totals.values, name="Valor del inventario", marker_color=BLUE,
        hovertemplate="%{x}<br>Inventario: $%{y:,.2~f} MXN<extra></extra>",
    ), secondary_y=False)
    if len(totals) and totals.sum() > 0 and (totals >= 0).all():
        fig.add_trace(go.Scatter(
            x=totals.index, y=totals.cumsum() / totals.sum() * 100,
            name="Porcentaje acumulado", mode="lines+markers", line=dict(color=TEAL, width=3),
            hovertemplate="Hasta %{x}<br>%{y:.1f}% del valor total<extra></extra>",
        ), secondary_y=True)
    fig.update_yaxes(title_text="Valor del inventario (MXN)", tickprefix="$", tickformat=",.0f", secondary_y=False)
    fig.update_yaxes(title_text="Acumulado", range=[0, 105], tickmode="array", tickvals=[0, 25, 50, 75, 100], ticksuffix="%", showgrid=False, secondary_y=True)
    fig.update_xaxes(title=None, tickangle=-25)
    return style_chart(fig)


def stock_consumption_chart(frame, limit=15):
    frame = frame.loc[~frame["item"].duplicated(keep=False)].dropna(subset=["item", "inventory", "monthly_demand"])
    rows = frame.groupby("item", as_index=False).agg(
        description=("description", "first"), inventory=("inventory", "sum"), monthly_demand=("monthly_demand", "sum"),
    )
    rows = rows.loc[rows["monthly_demand"] > 0].copy()
    rows["coverage"] = rows["inventory"] / rows["monthly_demand"]
    rows = rows.sort_values(["coverage", "monthly_demand"], ascending=[True, False]).head(limit)
    fig = go.Figure()
    for row in rows.itertuples():
        fig.add_shape(type="line", x0=row.inventory, x1=row.monthly_demand, y0=row.item, y1=row.item,
                      line=dict(color="#C7D7E7", width=4))
    details = rows[["description"]].copy()
    details["coverage"] = rows["coverage"].map(coverage_text)
    for col, label, color, symbol in [
        ("inventory", "Existencias actuales", BLUE, "circle"),
        ("monthly_demand", "Demanda mensual ajustada", AMBER, "diamond"),
    ]:
        fig.add_trace(go.Scatter(
            x=rows[col], y=rows["item"], name=label, mode="markers", customdata=details.to_numpy(),
            marker=dict(color=color, symbol=symbol, size=11),
            hovertemplate="%{y} · %{customdata[0]}<br>" + label + ": %{x:,.2~f} piezas"
                          "<br>Cobertura: %{customdata[1]}<extra></extra>",
        ))
    fig.update_xaxes(title="Piezas", tickformat=",.2~f", rangemode="tozero")
    fig.update_yaxes(type="category", categoryorder="array", categoryarray=rows["item"].tolist(), autorange="reversed", showgrid=False)
    return style_chart(fig, max(370, 32 * len(rows) + 120))


def coverage_priority_chart(frame, limit=15):
    rows = add_coverage_indicators(frame)
    rows = sort_by_coverage_priority(rows.loc[rows["coverage_calculable"]]).head(limit)
    fig = go.Figure()
    details = rows[["description", "coverage_status"]].copy()
    details["coverage_text"] = rows["coverage_months_calc"].map(coverage_text)
    fig.add_trace(go.Bar(
        x=rows["coverage_months_calc"], y=rows["item"], orientation="h",
        marker_color=[RED if priority else BLUE for priority in rows["coverage_priority"]],
        customdata=details.to_numpy(), text=details["coverage_text"], textposition="outside", cliponaxis=False,
        hovertemplate="%{y} · %{customdata[0]}<br>Cobertura: %{customdata[2]}<br>%{customdata[1]}<extra></extra>",
    ))
    # A zero-length bar still needs a visible marker and a usable hover target.
    fig.add_trace(go.Scatter(
        x=rows["coverage_months_calc"], y=rows["item"], mode="markers", showlegend=False,
        marker=dict(size=8, color=[RED if priority else BLUE for priority in rows["coverage_priority"]]),
        customdata=details.to_numpy(), hovertemplate="%{y} · %{customdata[0]}<br>Cobertura: %{customdata[2]}<br>%{customdata[1]}<extra></extra>",
    ))
    fig.add_vline(x=COVERAGE_PRIORITY_MONTHS, line_dash="dash", line_color=AMBER)
    maximum = max(COVERAGE_PRIORITY_MONTHS, rows["coverage_months_calc"].max()) if len(rows) else COVERAGE_PRIORITY_MONTHS
    fig.update_xaxes(title=f"Cobertura en meses · línea de referencia: {COVERAGE_PRIORITY_MONTHS:g} meses", range=[0, maximum * 1.35], tickformat=",.2~f")
    fig.update_yaxes(type="category", categoryorder="array", categoryarray=rows["item"].tolist(), autorange="reversed", showgrid=False)
    fig.update_layout(showlegend=False)
    return style_chart(fig, max(370, 32 * len(rows) + 120))


def capital_by_consumption_chart(frame):
    frame = add_coverage_indicators(frame).dropna(subset=["inventory_value"])
    valid = frame["coverage_calculable"] | frame["coverage_status"].eq("Sin consumo registrado")
    rows = frame.loc[valid & frame["inventory"].gt(0)].copy()
    coverage = rows["coverage_months_calc"]
    order = ["Menos de 1 mes", f"De 1 a menos de {COVERAGE_PRIORITY_MONTHS:g} meses", f"{COVERAGE_PRIORITY_MONTHS:g} meses o más", "Sin consumo registrado"]
    rows["band"] = np.select(
        [rows["monthly_demand"].eq(0).to_numpy(dtype=bool), coverage.lt(1).fillna(False).to_numpy(dtype=bool), coverage.lt(COVERAGE_PRIORITY_MONTHS).fillna(False).to_numpy(dtype=bool)],
        [order[3], order[0], order[1]], default=order[2],
    )
    totals = rows.groupby("band").agg(value=("inventory_value", "sum"), parts=("item", "nunique")).reindex(order, fill_value=0)
    fig = go.Figure(go.Bar(
        x=totals["value"], y=totals.index, orientation="h", marker_color=[RED, AMBER, BLUE, GRAY],
        customdata=totals[["parts"]], text=totals["value"], texttemplate="$%{text:,.0f} MXN", textposition="auto",
        hovertemplate="%{y}<br>Inventario: $%{x:,.2~f} MXN<br>%{customdata[0]:,.0f} refacciones<extra></extra>",
    ))
    fig.update_xaxes(title="Valor del inventario (MXN)", tickprefix="$", tickformat=",.0f", rangemode="tozero")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return style_chart(fig, 350)


def monthly_demand_matrix(frame):
    dated = frame.dropna(subset=["posting_date", "quantity"]).copy()
    if dated.empty:
        return pd.DataFrame(), dated
    dated["month"] = dated["posting_date"].dt.to_period("M")
    dated["order_status"] = dated["status"].map(status_label)
    monthly = dated.groupby(["month", "order_status"])["quantity"].sum().unstack(fill_value=0)
    # A missing month is a gap in the source, not a proven month with zero demand.
    monthly = monthly.reindex(pd.period_range(monthly.index.min(), monthly.index.max(), freq="M"))
    return monthly, dated


def month_labels(periods):
    return [f"{MONTHS[p.month - 1]} {p.year}" for p in periods]


def monthly_demand_chart(frame, percentage=False):
    monthly, _ = monthly_demand_matrix(frame)
    fig = go.Figure()
    for idx, label in enumerate(monthly.columns):
        units = monthly[label]
        values = units / monthly.sum(axis=1).replace(0, np.nan) * 100 if percentage else units
        fig.add_trace(go.Bar(
            x=month_labels(monthly.index), y=values, name=label, marker_color=STATUS_COLORS.get(label, PALETTE[idx % len(PALETTE)]),
            customdata=np.array(units).reshape(-1, 1),
            hovertemplate="%{x}<br>" + label + ": %{customdata[0]:,.2~f} piezas"
                          + ("<br>%{y:.1f}% del mes" if percentage else "") + "<extra></extra>",
        ))
    fig.update_layout(barmode="stack", bargap=0.25)
    fig.update_xaxes(title=None, type="category", tickangle=-30)
    fig.update_yaxes(title="Proporción de las piezas solicitadas" if percentage else "Piezas solicitadas",
                     tickformat=".0f" if percentage else ",.2~f", ticksuffix="%" if percentage else "", rangemode="tozero")
    if percentage:
        fig.update_yaxes(range=[0, 100])
    return style_chart(fig, 440)


def demand_heatmap(frame, limit=15):
    monthly, dated = monthly_demand_matrix(frame)
    fig = go.Figure()
    if dated.empty:
        return style_chart(fig)
    leaders = dated.groupby("item")["quantity"].sum().sort_values(ascending=False).head(limit).index
    matrix = dated.groupby(["item", "month"])["quantity"].sum().unstack(fill_value=0)
    matrix = matrix.reindex(index=leaders, columns=monthly.index)
    descriptions = dated.groupby("item")["description"].first().reindex(leaders).fillna("")
    fig.add_trace(go.Heatmap(
        x=month_labels(matrix.columns), y=matrix.index, z=matrix.to_numpy(),
        customdata=np.repeat(descriptions.to_numpy()[:, None], len(matrix.columns), axis=1),
        colorscale=[[0, "#F0F5FA"], [0.25, "#ADCBE2"], [0.6, "#4487B9"], [1, "#123D62"]],
        zmin=0, colorbar=dict(title="Piezas", tickformat=",.0f", thickness=12), hoverongaps=False,
        hovertemplate="%{y} · %{customdata}<br>%{x}: %{z:,.2~f} piezas<extra></extra>",
        xgap=2, ygap=2,
    ))
    fig.update_xaxes(title=None, type="category", tickangle=-30, showgrid=False)
    fig.update_yaxes(title="Código de refacción", type="category", autorange="reversed", showgrid=False)
    return style_chart(fig, max(360, len(matrix) * 30 + 130))


def logistics_status_chart(frame, percentage=False):
    rows = frame.dropna(subset=["quantity"]).copy()
    rows["origin_label"] = rows["origin"].fillna("Sin origen")
    rows["status_label"] = rows["status"].map(status_label)
    matrix = rows.groupby(["origin_label", "status_label"])["quantity"].sum().unstack(fill_value=0)
    matrix = matrix.loc[matrix.sum(axis=1).sort_values(ascending=False).index]
    fig = go.Figure()
    for idx, label in enumerate(matrix.columns):
        units = matrix[label]
        values = units / matrix.sum(axis=1).replace(0, np.nan) * 100 if percentage else units
        fig.add_trace(go.Bar(
            x=values, y=matrix.index, orientation="h", name=label,
            marker_color=STATUS_COLORS.get(label, PALETTE[idx % len(PALETTE)]),
            customdata=np.array(units).reshape(-1, 1),
            hovertemplate="%{y}<br>" + label + ": %{customdata[0]:,.2~f} piezas"
                          + ("<br>%{x:.1f}% de este origen" if percentage else "") + "<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Proporción de las piezas por origen" if percentage else "Piezas registradas en cada estado",
                     ticksuffix="%" if percentage else "", tickformat=".0f" if percentage else ",.0f", rangemode="tozero")
    if percentage:
        fig.update_xaxes(range=[0, 100])
    fig.update_yaxes(autorange="reversed", type="category", showgrid=False)
    return style_chart(fig, max(360, len(matrix) * 60 + 190))


def prepare_arrival_buckets(frame, reference_date):
    rows = frame.loc[~frame["status"].astype(str).str.strip().str.casefold().eq("completed")].copy()
    # Excel serial numbers and free-text ETAs are not safe to interpret as dates here.
    raw = rows["eta"].where(~rows["eta"].map(lambda value: isinstance(value, (int, float))))
    eta = pd.to_datetime(raw, errors="coerce", format="mixed").dt.normalize()
    days = (eta - pd.Timestamp(reference_date).normalize()).dt.days
    labels = ["Fecha vencida", "Llegada hoy o en 7 días", "Llegada después de 7 días", "Sin fecha válida"]
    rows["arrival_bucket"] = np.select(
        [eta.isna(), days < 0, days <= 7], [labels[3], labels[0], labels[1]], default=labels[2],
    )
    return rows, labels


def arrival_chart(frame, reference_date):
    frame = frame.dropna(subset=["quantity"])
    rows, labels = prepare_arrival_buckets(frame, reference_date)
    totals = rows.groupby("arrival_bucket").agg(quantity=("quantity", "sum"), invoices=("invoice", "nunique")).reindex(labels, fill_value=0)
    fig = go.Figure(go.Bar(
        x=totals["quantity"], y=totals.index, orientation="h", marker_color=[RED, AMBER, BLUE, GRAY],
        customdata=totals[["invoices"]], text=totals["quantity"], texttemplate="%{text:,.0f} piezas", textposition="auto",
        hovertemplate="%{y}<br>%{x:,.2~f} piezas en registros sin completar<br>%{customdata[0]:,.0f} facturas distintas<extra></extra>",
    ))
    fig.update_xaxes(title="Piezas en registros sin completar", tickformat=",.0f", rangemode="tozero")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return style_chart(fig, 350)


def catalog_link_chart(forecast, demand, transits):
    sources, distributions = [], []
    labels = ["Relación única", "Sin coincidencia", "Código repetido", "Sin código"]
    for label, rows in [("Demanda", demand), ("Logística", transits)]:
        if "item" not in rows or rows.empty:
            continue
        sources.append(label)
        distributions.append(catalog_matches(rows["item"], forecast).value_counts().reindex(labels, fill_value=0).tolist())
    counts_matrix = np.array(distributions).reshape(-1, len(labels))
    total = counts_matrix.sum(axis=1)
    fig = go.Figure()
    for index, (label, color) in enumerate(zip(labels, [TEAL, AMBER, RED, GRAY])):
        counts = counts_matrix[:, index]
        percent = counts / total * 100
        fig.add_trace(go.Bar(
            x=percent, y=sources, orientation="h", name=label, marker_color=color,
            text=percent, texttemplate="%{text:.1f}%", textposition="inside",
            customdata=np.column_stack([counts, total]),
            hovertemplate="%{y}<br>" + label + ": %{customdata[0]:,.0f} de %{customdata[1]:,.0f} registros<br>%{x:.1f}%<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Registros relacionados por código de refacción", range=[0, 100], ticksuffix="%")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return style_chart(fig, 300)
