"""Privacy-by-default and deterministic demonstration fixtures."""
import unittest
from unittest.mock import patch

import pandas as pd

from src.demo_data import make_demo_data
from src.data_pipeline import enrich_forecast
from src.models import segment_inventory


class DemoDataTests(unittest.TestCase):
    def test_demo_is_reproducible_and_independent(self):
        first = make_demo_data()
        second = make_demo_data()
        for left, right in zip(first, second):
            pd.testing.assert_frame_equal(left, right)
        first[0].loc[0, 'inventory'] = 999999
        self.assertEqual(second[0].loc[0, 'inventory'], 0)

    def test_every_nonempty_part_code_is_explicitly_fictitious(self):
        for frame in make_demo_data():
            self.assertTrue(frame.item.dropna().str.startswith('DEMO-').all())
            self.assertTrue(frame.source_row.ge(2).all())
        self.assertEqual([len(frame) for frame in make_demo_data()], [43, 120, 50])

    def test_generator_does_not_load_workbooks(self):
        with patch('src.data_pipeline.load_workbook', side_effect=AssertionError('No disk input')):
            self.assertEqual(len(make_demo_data()), 3)

    def test_quality_examples_and_attention_boundary(self):
        result = enrich_forecast(make_demo_data()[0])
        self.assertEqual(int(result.catalog_eligible.sum()), 40)
        self.assertEqual(int(result.duplicate_item.sum()), 2)
        self.assertTrue(result.loc[result.item.eq('DEMO-005'), 'coverage_priority'].item())
        self.assertFalse(result.loc[result.item.eq('DEMO-006'), 'coverage_priority'].item())
        self.assertTrue(result.loc[result.item.eq('DEMO-037'), 'coverage_months_calc'].isna().all())

    def test_models_only_evaluate_complete_unique_records(self):
        result, engine = segment_inventory(enrich_forecast(make_demo_data()[0]))
        self.assertIn('KMeans', engine)
        self.assertTrue(result.loc[~result.catalog_eligible, 'anomaly'].isna().all())
        self.assertTrue(result.loc[result.item.eq('DEMO-037'), 'anomaly'].isna().all())


if __name__ == '__main__':
    unittest.main()
