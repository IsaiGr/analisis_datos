import unittest

import numpy as np
import pandas as pd

from src.dashboard_charts import (
    arrival_chart, capital_by_consumption_chart, catalog_link_chart, demand_heatmap,
    inventory_concentration_chart, logistics_status_chart, monthly_demand_chart,
    prepare_arrival_buckets, priority_purchase_chart, stock_consumption_chart,
)


class DashboardChartTests(unittest.TestCase):
    def setUp(self):
        self.forecast = pd.DataFrame({
            "item": ["A", "B", "C"], "description": ["Pieza A", "Pieza B", "Pieza C"],
            "family": ["F1", "F2", "F2"], "priority": ["Alta", "Alta", "Baja"],
            "inventory": [0, 4, 10], "monthly_demand": [5, 2, 0],
            "inventory_value": [0, 40, 100], "purchase_amount": [50, 20, 0],
        })
        self.demand = pd.DataFrame({
            "item": ["A", "A", "B", "UNKNOWN"], "description": ["Pieza A", "Pieza A", "Pieza B", "Sin catálogo"],
            "posting_date": pd.to_datetime(["2026-01-01", "2026-03-01", "2026-03-02", None]),
            "status": ["APPROVED", "APPROVED", "Canceled", "Back Order"], "quantity": [10, 20, 5, 7],
        })
        self.transits = pd.DataFrame({
            "item": ["A", "A", "B", "B", "UNKNOWN", "A"], "invoice": ["I1", "I2", "I3", "I4", "I5", "I6"],
            "origin": ["China"] * 6, "status": ["Completed", "PARTIAL INBOUND"] + ["Pending Inbound"] * 4,
            "eta": ["2026-10-01", "2026-10-01", "2026-10-09", "2026-11-01", "Por confirmar", 45000],
            "quantity": [100, 20, 30, 40, 50, 60],
        })

    def test_inventory_charts_preserve_money_and_rank_coverage(self):
        priority = priority_purchase_chart(self.forecast)
        self.assertAlmostEqual(sum(priority.data[0].x), 70)
        concentration = inventory_concentration_chart(self.forecast)
        self.assertAlmostEqual(sum(concentration.data[0].y), 140)
        self.assertAlmostEqual(concentration.data[1].y[-1], 100)
        capital = capital_by_consumption_chart(self.forecast)
        self.assertAlmostEqual(sum(capital.data[0].x), 140)
        self.assertEqual(capital.data[0].x[-1], 100)
        comparison = stock_consumption_chart(self.forecast)
        self.assertEqual(list(comparison.data[0].y), ["A", "B"])
        self.assertEqual(list(comparison.data[0].x), [0, 4])
        self.assertEqual(list(comparison.data[1].x), [5, 2])

    def test_monthly_charts_keep_missing_month_as_gap(self):
        chart = monthly_demand_chart(self.demand)
        self.assertEqual(list(chart.data[0].x), ["ene 2026", "feb 2026", "mar 2026"])
        self.assertAlmostEqual(sum(np.nansum(trace.y) for trace in chart.data), 35)
        self.assertTrue(all(np.isnan(trace.y[1]) for trace in chart.data))
        percent = monthly_demand_chart(self.demand, percentage=True)
        for month in [0, 2]:
            self.assertAlmostEqual(sum(trace.y[month] for trace in percent.data), 100)
        heatmap = demand_heatmap(self.demand)
        self.assertTrue(np.isnan(heatmap.data[0].z[:, 1]).all())
        self.assertAlmostEqual(np.nansum(heatmap.data[0].z), 35)

    def test_logistics_keeps_partial_status_and_dates_conserve_quantities(self):
        status = logistics_status_chart(self.transits)
        self.assertAlmostEqual(sum(sum(trace.x) for trace in status.data), 300)
        self.assertIn("Ingreso parcial", [trace.name for trace in status.data])
        percent = logistics_status_chart(self.transits, percentage=True)
        self.assertAlmostEqual(sum(trace.x[0] for trace in percent.data), 100)
        rows, _ = prepare_arrival_buckets(self.transits, "2026-10-09")
        self.assertNotIn("I1", rows["invoice"].tolist())
        self.assertEqual(rows.groupby("arrival_bucket")["quantity"].sum().to_dict(), {
            "Fecha vencida": 20, "Llegada hoy o en 7 días": 30,
            "Llegada después de 7 días": 40, "Sin fecha válida": 110,
        })
        self.assertAlmostEqual(sum(arrival_chart(self.transits, "2026-10-09").data[0].x), 200)

    def test_catalog_chart_does_not_hide_unmatched_rows(self):
        chart = catalog_link_chart(self.forecast, self.demand, self.transits)
        self.assertAlmostEqual(chart.data[0].x[0], 75)
        self.assertAlmostEqual(chart.data[1].x[0], 25)
        self.assertAlmostEqual(chart.data[0].x[1] + chart.data[1].x[1], 100)

    def test_empty_selections_can_be_serialized(self):
        forecast, demand, transits = self.forecast.iloc[:0], self.demand.iloc[:0], self.transits.iloc[:0]
        figures = [priority_purchase_chart(forecast), inventory_concentration_chart(forecast),
                   stock_consumption_chart(forecast), capital_by_consumption_chart(forecast),
                   monthly_demand_chart(demand), demand_heatmap(demand),
                   logistics_status_chart(transits), arrival_chart(transits, "2026-10-09"),
                   catalog_link_chart(forecast, demand, transits)]
        for fig in figures:
            self.assertIn('"data":', fig.to_json())

    def test_catalog_chart_separates_ambiguous_from_unique(self):
        catalog = pd.concat([self.forecast, self.forecast.iloc[:1]], ignore_index=True)
        chart = catalog_link_chart(catalog, self.demand, self.transits)
        self.assertEqual([trace.name for trace in chart.data], ['Relación única', 'Sin coincidencia', 'Código repetido', 'Sin código'])
        self.assertAlmostEqual(chart.data[0].x[0], 25)
        self.assertAlmostEqual(chart.data[2].x[0], 50)
        self.assertAlmostEqual(sum(trace.x[0] for trace in chart.data), 100)

    def test_unknown_consumption_is_not_classed_as_excess_or_zero(self):
        frame = self.forecast.copy()
        frame.loc[1, 'monthly_demand'] = np.nan
        capital = capital_by_consumption_chart(frame)
        self.assertEqual(sum(capital.data[0].x), 100)
        stock = stock_consumption_chart(frame)
        self.assertEqual(list(stock.data[0].y), ['A'])
        frame['purchase_amount'] = np.nan
        self.assertEqual(len(priority_purchase_chart(frame).data[0].x), 0)

    def test_tooltips_keep_contrast_for_dark_background(self):
        chart = stock_consumption_chart(self.forecast)
        self.assertEqual(chart.layout.hoverlabel.bgcolor, '#F8FAFC')
        self.assertEqual(chart.layout.hoverlabel.font.color, '#102A43')
        self.assertTrue(all(trace.hoverlabel.font.color == '#102A43' for trace in chart.data))


if __name__ == "__main__":
    unittest.main()
