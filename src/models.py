from __future__ import annotations

import numpy as np
import pandas as pd


def segment_inventory(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Use KMeans/IsolationForest when available; retain a deterministic fallback."""
    out = df.copy()
    features = ["inventory", "monthly_demand", "inventory_value", "lead_time", "shortage_gap"]
    out["segment"] = "No evaluado: datos por revisar"
    out["anomaly"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    if not set(features).issubset(out):
        return out, "Sin datos completos para evaluar"
    x = out[features].replace([np.inf, -np.inf], np.nan)
    valid = x.notna().all(axis=1) & x.ge(0).all(axis=1)
    if "catalog_eligible" in out:
        valid &= out["catalog_eligible"]
    x = x.loc[valid]
    if len(x) < 12 or len(x.drop_duplicates()) < 2:
        return out, "Datos completos insuficientes para modelos exploratorios"
    try:
        from sklearn.cluster import KMeans
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler
        z = StandardScaler().fit_transform(x)
        k = min(5, max(2, len(x) // 500), len(x.drop_duplicates()))
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(z)
        out.loc[valid, "segment"] = [f"Grupo exploratorio {label + 1}" for label in labels]
        out.loc[valid, "anomaly"] = IsolationForest(contamination=min(0.05, max(0.01, 10 / len(x))), random_state=42).fit_predict(z) == -1
        return out, f"KMeans ({k} grupos) + Isolation Forest; {len(x):,} filas completas evaluadas"
    except ImportError:
        out.loc[valid, "segment"] = np.select(
            [out.loc[valid, "shortage_gap"] > 0, out.loc[valid, "coverage_months_calc"] > 12, out.loc[valid, "monthly_demand"] <= 0],
            ["Faltante bruto estimado", "Cobertura mayor a 12 meses", "Sin consumo registrado"], default="Otros casos evaluables"
        )
        return out, "Reglas de respaldo (instalar scikit-learn para modelos)"


def model_readiness(df: pd.DataFrame) -> list[dict]:
    return [
        {"model": "KMeans", "status": "Exploratorio; no determina compras", "use": "Agrupar únicamente registros completos y códigos únicos"},
        {"model": "Isolation Forest", "status": "Exploratorio; no es probabilidad de falla", "use": "Señalar casos para revisar; sin datos no hay evaluación"},
        {"model": "Random Forest", "status": "Pendiente de históricos etiquetados", "use": "Predicción de riesgo de desabasto"},
        {"model": "Keras/PyTorch", "status": "Pendiente de mayor historia temporal", "use": "Pronóstico avanzado"},
        {"model": "SARSA", "status": "Pendiente de simulador validado", "use": "Política de reabastecimiento"},
    ]
