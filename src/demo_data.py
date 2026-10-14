"""Entirely invented, deterministic data. No files, network or private sources.

Values are teaching examples, not anonymized or rescaled business records.
Some deliberate missing/duplicate records exercise the quality review.
"""
from datetime import date

import numpy as np
import pandas as pd

from src.data_pipeline import _normalize

DEMO_REFERENCE_DATE = date(2026, 6, 15)


def _prepare(records, numeric, source, sheet, first_row):
    frame = pd.DataFrame(records)
    columns = list(frame.columns)
    frame["source_sheet"] = sheet
    frame["source_row"] = range(first_row, first_row + len(frame))
    return _normalize(frame, {column: column for column in columns}, set(numeric), source)


def make_demo_data():
    """Return forecast, demand and inbound records in the normalized app schema."""
    families = ["Bombas", "Sensores", "Filtros", "Motores"]
    stocks = [0, 5, 12, 25, 39, 40, 55, 80, 140, 220]
    records = []
    for index in range(40):
        demand = 10.0 if index < 30 else [0.0, 5.0, 20.0, 0.0, 10.0][index % 5]
        stock = float(stocks[index % 10])
        lead = float([2, 3, 5, 6][index % 4])
        cost = float(25 + 15 * (index % 12))
        proposal = float(max(0, demand * lead - stock))
        records.append({
            "item": f"DEMO-{index + 1:03d}", "description": f"Refacción ficticia {index + 1:03d}",
            "family": families[index % 4], "category": f"Línea demo {index % 2 + 1}",
            "customer_model": f"Modelo demo {index % 3 + 1}", "origin": f"Proveedor demo {index % 3 + 1}",
            "key_component": "Sí" if index % 4 == 0 else "No",
            "inventory": stock, "monthly_demand": demand, "lead_time": lead,
            "unit_cost_mxn": cost, "inventory_value": stock * cost,
            "on_order": float((index % 4) * 5), "recommended_qty": proposal,
            "purchase_amount": proposal * cost, "reorder_point": demand * lead,
            "reorder_flag": "Sí" if proposal else "No",
            "priority": "Revisar" if proposal else "Seguimiento",
            "abc_class": ["A", "B", "C"][index % 3],
            "inventory_health": "Sin movimiento" if demand == 0 else ("Lento" if stock > 100 else "Activo"),
            "support_status": "Ejemplo", "nom_status": "Ejemplo", "purchase_decision": "Revisión manual",
            "avg_back_order_3m": float(index % 3),
        })
    # Deliberate quality examples, not mistakes taken from a real workbook.
    records[35]["monthly_demand"] = np.nan
    records[36]["inventory"] = np.nan
    records[36]["inventory_value"] = np.nan
    records[37]["purchase_amount"] += 1.0
    for sequence in (1, 2):
        records.append(dict(records[0], item="DEMO-DUP", description=f"Duplicado ficticio {sequence}"))
    records.append(dict(records[1], item=None, description="Ejemplo sin código"))
    forecast = _prepare(records, [
        "inventory", "monthly_demand", "lead_time", "unit_cost_mxn", "inventory_value",
        "on_order", "recommended_qty", "purchase_amount", "reorder_point", "avg_back_order_3m",
    ], "forecast", "1. FORECAST", 5)

    order_records = []
    for index in range(120):
        part = index % 40 + 1
        day = pd.Timestamp("2026-01-05") + pd.Timedelta(days=index)
        order_records.append({
            "item": f"DEMO-{part:03d}", "description": f"Refacción ficticia {part:03d}",
            "customer_model": f"Modelo demo {index % 3 + 1}", "factory_model": "Modelo ficticio",
            "key_component": "No", "sales_order": f"ORD-DEMO-{index + 1:03d}",
            "status": ["APPROVED", "Back Order", "Canceled", "APPROVED"][index % 4],
            "quantity": float(index % 5 + 1), "posting_date": day, "created_date": day,
            "week": str(day.isocalendar().week),
        })
    order_records[-1]["item"] = "DEMO-SIN-RELACION"
    order_records[-2]["item"] = "DEMO-DUP"
    demand = _prepare(order_records, ["quantity"], "demand", "Free Sales", 3)

    inbound_records = []
    anchor = pd.Timestamp(DEMO_REFERENCE_DATE)
    for index in range(50):
        part = index % 40 + 1
        quantity = float((index % 6 + 1) * 5)
        unit_price = float(index % 7 + 2)
        inbound_records.append({
            "item": f"DEMO-{part:03d}", "description": f"Refacción ficticia {part:03d}",
            "quantity": quantity, "unit_price_usd": unit_price, "invoice_amount_usd": quantity * unit_price,
            "container": f"GUIA-DEMO-{index + 1:03d}", "invoice": f"FAC-DEMO-{index + 1:03d}",
            "origin": f"Proveedor demo {index % 3 + 1}", "category": f"Línea demo {index % 2 + 1}",
            "eta": (anchor + pd.Timedelta(days=[-10, -2, 0, 5, 20][index % 5])).strftime("%Y-%m-%d"),
            "status": ["Completed", "Pending Inbound", "In Transit", "Partial Inbound", "Pending Dispatch"][index % 5],
        })
    inbound_records[-1]["eta"] = "Por confirmar"
    inbound_records[-2]["item"] = "DEMO-SIN-RELACION"
    transits = _prepare(inbound_records, ["quantity", "unit_price_usd", "invoice_amount_usd"], "transits", "INBOUND", 2)
    return forecast, demand, transits
