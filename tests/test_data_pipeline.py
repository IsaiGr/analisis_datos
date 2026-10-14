from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd
from openpyxl import Workbook

from src.data_pipeline import (
    _normalize, _read_cached_sheet, add_forecast_context, apply_filters,
    catalog_matches, data_issues, enrich_forecast, file_signature,
    load_demand, load_forecast, load_transits, pending_demand, strict_sum,
)
from src.models import segment_inventory


def workbook_bytes(sheet, header_row, headers, rows):
    workbook = Workbook()
    page = workbook.active
    page.title = sheet
    for _ in range(header_row):
        page.append([None])
    page.append(headers)
    for row in rows:
        page.append(row)
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


class BusinessLogicTests(unittest.TestCase):
    def forecast(self):
        return pd.DataFrame({
            'item': ['A', 'B', 'C', 'D'], 'inventory': [29., 0., 4., 5.],
            'monthly_demand': [37 / 3, 0., np.nan, 2.], 'lead_time': [5., 3., 3., 3.],
            'recommended_qty': [2., 0., 1., 1.], 'unit_cost_mxn': [10., 5., np.nan, 10.],
            'purchase_amount': [20., 0., 9., 20.], 'inventory_value': [290., 0., 20., 50.],
        })

    def test_monthly_lead_time_and_unknown_are_not_zero(self):
        result = enrich_forecast(self.forecast())
        self.assertAlmostEqual(result.at[0, 'demand_during_lead_time'], 61 + 2 / 3)
        self.assertAlmostEqual(result.at[0, 'shortage_gap'], 32 + 2 / 3)
        self.assertEqual(result.at[1, 'shortage_gap'], 0)
        self.assertTrue(pd.isna(result.at[2, 'shortage_gap']))
        self.assertFalse(result.at[2, 'risk_calculable'])
        self.assertTrue(pd.isna(result.at[1, 'coverage_months_calc']))

    def test_negative_or_infinite_inputs_cannot_mean_no_risk(self):
        frame = self.forecast()
        frame.loc[0, 'inventory'] = -1
        frame.loc[1, 'lead_time'] = np.inf
        frame.loc[3, 'monthly_demand'] = -2
        result = enrich_forecast(frame)
        self.assertTrue(result.shortage_gap.isna().all())

    def test_duplicate_keys_are_excluded_before_filters(self):
        frame = pd.concat([self.forecast(), self.forecast().iloc[:1]], ignore_index=True)
        result = enrich_forecast(frame)
        self.assertEqual(result.duplicate_item.sum(), 2)
        self.assertTrue(result.loc[result.item.eq('A'), 'shortage_gap'].isna().all())
        self.assertEqual(result.catalog_eligible.sum(), 3)
        # Filtering down to one copy must not retroactively make the code unique.
        self.assertFalse(result.iloc[0].catalog_eligible)

    def test_purchase_check_does_not_rewrite_source_proposal(self):
        result = enrich_forecast(self.forecast())
        self.assertTrue(result.at[0, 'purchase_amount_consistent'])
        self.assertTrue(pd.isna(result.at[2, 'purchase_amount_consistent']))
        self.assertFalse(result.at[3, 'purchase_amount_consistent'])
        self.assertEqual(result.at[3, 'purchase_amount'], 20)

    def test_catalog_link_does_not_choose_or_multiply_duplicates(self):
        forecast = pd.DataFrame({'item': ['A', 'A', 'B', None], 'family': ['F1', 'F2', 'F3', 'BAD'], 'origin': ['China'] * 4})
        source = pd.DataFrame({'item': ['A', 'B', 'Z', None, '  B  '], 'quantity': [1, 2, 3, 4, 5], 'origin': ['USA', None, None, None, None]})
        source.attrs['issues'] = [{'issue': 'original'}]
        result = add_forecast_context(source, forecast)
        self.assertEqual(len(result), len(source))
        self.assertEqual(result.quantity.sum(), source.quantity.sum())
        self.assertEqual(result.catalog_match.tolist(), ['Código repetido', 'Relación única', 'Sin coincidencia', 'Sin código', 'Relación única'])
        self.assertTrue(pd.isna(result.at[0, 'family']))
        self.assertTrue(pd.isna(result.at[3, 'family']))
        self.assertEqual(result.at[0, 'origin'], 'USA')
        self.assertEqual(result.at[1, 'family'], 'F3')
        self.assertEqual(result.at[4, 'origin'], 'China')
        self.assertEqual(result.attrs, source.attrs)

    def test_pending_counts_status_not_three_month_average(self):
        frame = pd.DataFrame({'status': ['Back Order', ' back_order ', 'APPROVED', 'Canceled'], 'quantity': [92., 3., 100., 200.], 'avg_back_order_3m': [999.] * 4})
        result = pending_demand(frame)
        self.assertEqual(result['quantity'], 95)
        self.assertEqual(result['rows'], 2)
        frame.loc[0, 'quantity'] = np.nan
        self.assertTrue(np.isnan(pending_demand(frame)['quantity']))
        self.assertTrue(np.isnan(pending_demand(frame.drop(columns='status'))['quantity']))
        self.assertEqual(pending_demand(frame.iloc[:0])['quantity'], 0)
        frame['status'] = None
        self.assertTrue(np.isnan(pending_demand(frame)['quantity']))

    def test_numeric_codes_match_without_removing_text_leading_zeros(self):
        forecast = pd.DataFrame({'item': [123., 456.]})
        result = catalog_matches(pd.Series(['123', '00123', None, '#VALUE!']), forecast)
        self.assertEqual(result.tolist(), ['Relación única', 'Sin coincidencia', 'Sin código', 'Sin código'])

    def test_sum_never_treats_unknown_as_zero(self):
        self.assertTrue(np.isnan(strict_sum(pd.Series([3., np.nan]))))
        self.assertTrue(np.isnan(strict_sum(pd.Series([np.inf]))))
        self.assertEqual(strict_sum(pd.Series([0., 0.])), 0)
        self.assertEqual(strict_sum(pd.Series([], dtype=float)), 0)

    def test_all_filters_and_risk_apply_across_sources(self):
        catalog = pd.DataFrame({'item': ['A', 'B'], 'family': ['F1', 'F2'], 'origin': ['China', 'USA'], 'category': ['C1', 'C2'], 'priority': ['Alta', 'Baja'], 'abc_class': ['A', 'C']})
        detail = add_forecast_context(pd.DataFrame({'item': ['A', 'B', 'Z'], 'status': ['Back Order'] * 3, 'quantity': [1., 2., 3.]}), catalog)
        options = {col: list(catalog[col]) + ['Sin relación / sin dato'] for col in ['family', 'origin', 'category', 'priority', 'abc_class']}
        for col in options:
            selections = dict(options)
            selections[col] = [catalog.at[0, col]]
            for frame in [catalog, detail, detail.copy()]:
                self.assertEqual(apply_filters(frame, selections, options).item.tolist(), ['A'])
        self.assertEqual(len(apply_filters(detail, options, options)), 3)
        self.assertEqual(pending_demand(apply_filters(detail, options, options, ['B']))['quantity'], 2)
        self.assertTrue(apply_filters(detail, {'family': []}, options).empty)
        self.assertTrue(apply_filters(pd.DataFrame({'quantity': [1]}), {'family': ['F1']}, options).empty)
        self.assertEqual(apply_filters(detail, {'family': ['Sin relación / sin dato']}, options).item.tolist(), ['Z'])

    def test_missing_values_do_not_enter_models_as_zero(self):
        frame = enrich_forecast(self.forecast())
        result, _ = segment_inventory(frame)
        self.assertTrue(result.anomaly.isna().all())
        self.assertTrue(result.segment.str.startswith('No evaluado').all())


class IngestionTests(unittest.TestCase):
    def test_excel_row_and_original_error_survive_normalizing(self):
        content = workbook_bytes('Test', 1, ['Item', 'Cantidad'], [['A', 0], [None, None], [None, '-'], ['C', '#VALUE!'], ['D', -2], ['E', 'incorrecto']])
        raw = _read_cached_sheet(content, 'Test', header_row=1)
        result = _normalize(raw, {'Item': 'item', 'Cantidad': 'quantity'}, {'quantity'}, 'test')
        self.assertEqual(result.source_row.tolist(), [3, 5, 6, 7, 8])
        self.assertEqual(result.at[0, 'quantity'], 0)
        self.assertTrue(result.quantity.iloc[1:].isna().all())
        self.assertTrue(pd.isna(result.at[1, 'item']))
        issues = data_issues(result)
        self.assertTrue(((issues.row == 6) & (issues.raw == '#VALUE!') & (issues.issue == 'Error de Excel')).any())
        self.assertTrue(((issues.row == 7) & (issues.raw == '-2')).any())

    def test_average_backorder_has_its_own_name(self):
        content = workbook_bytes('1. FORECAST', 3, ['Item', 'Avg Back\nOrder (3M)'], [['A', 12.5], ['B', '-']])
        result = load_forecast(content)
        self.assertEqual(result.at[0, 'avg_back_order_3m'], 12.5)
        self.assertTrue(pd.isna(result.at[1, 'avg_back_order_3m']))
        self.assertNotIn('back_order', result)
        self.assertTrue(result.inventory.isna().all())
        self.assertIn('Columna ausente', data_issues(result).issue.tolist())

    def test_demand_missing_code_and_quantity_are_not_invented(self):
        content = workbook_bytes('Free Sales', 1, ['Parts ID', 'User Status', 'Quantity', 'Posting Date'], [[None, 'Back Order', None, 45000], ['A', 'APPROVED', 0, '2026-10-01']])
        result = load_demand(content)
        self.assertTrue(pd.isna(result.at[0, 'item']))
        self.assertTrue(pd.isna(result.at[0, 'posting_date']))
        self.assertTrue(np.isnan(pending_demand(result)['quantity']))
        self.assertEqual(result.at[1, 'quantity'], 0)

    def test_malformed_inbound_is_not_replaced_by_summary(self):
        content = workbook_bytes('INBOUND', 0, ['PART. NO.', 'STATUS'], [['A', 'COMPLETED']])
        result = load_transits(content)
        self.assertEqual(result.source_sheet.tolist(), ['INBOUND'])
        self.assertTrue(result.quantity.isna().all())
        self.assertTrue(result.invoice_amount_usd.isna().all())

    def test_file_signature_changes_when_source_is_replaced(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'test.xlsx'
            path.write_bytes(b'test')
            before = file_signature(path)
            path.write_bytes(b'new version')
            self.assertNotEqual(before, file_signature(path))


if __name__ == '__main__':
    unittest.main()
