"""The four-month attention rule is independent of the Excel purchase proposal."""
import unittest

import numpy as np
import pandas as pd

from src.data_pipeline import (
    COVERAGE_PRIORITY_LABEL, add_coverage_indicators, apply_filters,
    coverage_text, enrich_forecast, sort_by_coverage_priority,
)
from src.dashboard_charts import BLUE, RED, capital_by_consumption_chart, coverage_priority_chart


class CoveragePriorityTests(unittest.TestCase):
    def frame(self, stock, demand):
        return pd.DataFrame({
            "item": [f"P{i}" for i in range(len(stock))],
            "description": [f"Refacción {i}" for i in range(len(stock))],
            "inventory": stock, "monthly_demand": demand,
        })

    def test_strict_threshold_without_rounding(self):
        result = add_coverage_indicators(self.frame([0., 3.5, 3.999, 4., 4.001], [1.] * 5))
        self.assertEqual(result.coverage_priority.tolist(), [True, True, True, False, False])
        self.assertEqual(result.coverage_status.iloc[:3].tolist(), [COVERAGE_PRIORITY_LABEL] * 3)
        self.assertEqual(result.coverage_months_calc.tolist(), [0., 3.5, 3.999, 4., 4.001])

    def test_zero_missing_negative_and_infinite_inputs_are_not_zero_coverage(self):
        frame = self.frame([2., np.nan, -1., np.inf, 2., 2., 2., 0.],
                           [0., 1., 1., 1., np.nan, -1., np.inf, 0.])
        result = add_coverage_indicators(frame)
        self.assertFalse(result.coverage_calculable.any())
        self.assertTrue(result.coverage_months_calc.isna().all())
        self.assertTrue(result.coverage_priority.isna().all())
        self.assertEqual(result.at[0, "coverage_status"], "Sin consumo registrado")
        self.assertEqual(result.at[7, "coverage_status"], "Sin consumo registrado")
        self.assertTrue(result.coverage_status.iloc[1:7].eq("Sin datos para calcular").all())

    def test_nullable_numbers_keep_unknown_state(self):
        frame = self.frame([0, None, 4, 5], [1, 1, None, 0])
        frame[["inventory", "monthly_demand"]] = frame[["inventory", "monthly_demand"]].astype("Float64")
        result = add_coverage_indicators(frame)
        self.assertTrue(result.at[0, "coverage_priority"])
        self.assertTrue(result.coverage_priority.iloc[1:].isna().all())
        self.assertEqual(result.coverage_calculable.tolist(), [True, False, False, False])

    def test_duplicate_and_missing_codes_never_acquire_priority(self):
        frame = self.frame([1.] * 4, [1.] * 4)
        frame["item"] = ["A", " A ", None, "B"]
        result = enrich_forecast(frame)
        self.assertTrue(result.coverage_priority.iloc[:3].isna().all())
        self.assertTrue(result.coverage_status.iloc[:3].eq("Código por revisar").all())
        self.assertTrue(result.at[3, "coverage_priority"])
        # Keeping only one duplicate after a filter must not rehabilitate it.
        after_filter = add_coverage_indicators(result.iloc[:1])
        self.assertTrue(after_filter.coverage_priority.isna().all())

    def test_coverage_is_independent_of_lead_time_and_source_purchase_priority(self):
        frame = self.frame([3., 4.5], [1., 1.])
        frame["lead_time"] = [np.nan, 5.]
        frame["on_order"] = [1000., 0.]
        frame["priority"] = ["Baja", "Alta"]
        frame["purchase_amount"] = [0., 90000.]
        frame["recommended_qty"] = [0., 10.]
        frame["unit_cost_mxn"] = [10., 9000.]
        result = enrich_forecast(frame)
        self.assertEqual(result.coverage_priority.tolist(), [True, False])
        self.assertTrue(pd.isna(result.at[0, "shortage_gap"]))
        self.assertEqual(result.at[1, "shortage_gap"], 0.5)
        pd.testing.assert_frame_equal(result[frame.columns], frame, check_dtype=False)

    def test_priority_ranking_precedes_money_and_unknowns_are_last(self):
        frame = self.frame([4., 3.5, np.nan, 0., 3.5], [1.] * 5)
        frame["purchase_amount"] = [999999., 100., 999999., 0., 0.]
        frame["shortage_gap"] = [0., 2., np.nan, 0., 3.]
        ranked = sort_by_coverage_priority(add_coverage_indicators(frame))
        self.assertEqual(ranked.item.tolist(), ["P3", "P4", "P1", "P0", "P2"])

    def test_coverage_filter_reaches_all_sources_and_intersects_other_filters(self):
        catalog = add_coverage_indicators(self.frame([2., 3., 4., np.nan], [1.] * 4))
        catalog["family"] = ["F1", "F2", "F1", "F1"]
        detail = pd.DataFrame({"item": ["P0", "P1", "P2", "P3", "Z", None],
                               "family": ["F1", "F2", "F1", "F1", None, None]})
        codes = catalog.loc[catalog.coverage_priority.fillna(False), "item"]
        options = {"family": ["F1", "F2", "Sin relación / sin dato"]}
        for frame in [catalog, detail, detail.copy()]:
            self.assertEqual(apply_filters(frame, options, options, coverage_items=codes).item.tolist(), ["P0", "P1"])
            self.assertEqual(apply_filters(frame, options, options, ["P1", "P2"], codes).item.tolist(), ["P1"])
            self.assertEqual(apply_filters(frame, {"family": ["F1"]}, options, coverage_items=codes).item.tolist(), ["P0"])
            self.assertTrue(apply_filters(frame, options, options, coverage_items=[]).empty)
        self.assertTrue(apply_filters(pd.DataFrame({"quantity": [1.]}), options, options, coverage_items=codes).empty)

    def test_display_does_not_round_priority_to_four_or_positive_stock_to_zero(self):
        cases = [(0., "0 meses"), (3., "3 meses"), (3.25, "3.25 meses"),
                 (3.999, "< 4 meses"), (4., "4 meses"), (0.0001, "< 0.01 meses"),
                 (np.nan, "No calculable"), (np.inf, "No calculable")]
        for value, expected in cases:
            self.assertEqual(coverage_text(value), expected)

    def test_chart_shows_threshold_and_zero_stock_marker(self):
        frame = self.frame([4., 3.999, 0., 3., 2.], [1., 1., 1., 0., np.nan])
        chart = coverage_priority_chart(frame)
        self.assertEqual(list(chart.data[0].y), ["P2", "P1", "P0"])
        self.assertEqual(list(chart.data[0].marker.color), [RED, RED, BLUE])
        self.assertEqual(list(chart.data[1].x), [0., 3.999, 4.])
        self.assertEqual(chart.data[0].text[1], "< 4 meses")
        self.assertEqual(chart.layout.shapes[0].x0, 4.)
        self.assertEqual(chart.layout.shapes[0].x1, 4.)
        self.assertEqual(chart.layout.hoverlabel.font.color, "#102A43")

    def test_chart_empty_and_all_unknown_are_serializable(self):
        frame = self.frame([1., 2.], [0., np.nan])
        for sample in [frame, frame.iloc[:0]]:
            chart = coverage_priority_chart(sample)
            self.assertEqual(len(chart.data[0].x), 0)
            self.assertIn('"data":', chart.to_json())

    def test_capital_bands_conserve_money_and_use_strict_four_month_boundary(self):
        frame = self.frame([0.5, 3.999, 4., 4.001, 5., 5.], [1., 1., 1., 1., 0., np.nan])
        frame["inventory_value"] = [5., 10., 15., 20., 25., 999.]
        chart = capital_by_consumption_chart(frame)
        self.assertEqual(list(chart.data[0].x), [5., 10., 35., 25.])
        self.assertEqual(sum(chart.data[0].x), 75.)
        self.assertEqual(list(chart.data[0].y), ["Menos de 1 mes", "De 1 a menos de 4 meses", "4 meses o más", "Sin consumo registrado"])


if __name__ == "__main__":
    unittest.main()
