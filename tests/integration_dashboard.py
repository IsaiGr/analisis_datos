"""Integration check using only invented data; never reads local workbooks.

Run: python -m unittest discover -s tests -p integration_dashboard.py -v
"""
from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from src.data_pipeline import COVERAGE_PRIORITY_LABEL
from src.demo_data import make_demo_data


class DashboardIntegration(unittest.TestCase):
    def setUp(self):
        environment = patch.dict('os.environ', {'REFACCIONES_ENABLE_UPLOADS': '0'})
        environment.start()
        self.addCleanup(environment.stop)
        for loader in ['load_forecast', 'load_demand', 'load_transits']:
            reader = patch('src.data_pipeline.' + loader, side_effect=AssertionError('Demo must not read workbooks'))
            reader.start()
            self.addCleanup(reader.stop)

    def test_demo_filters_quality_and_no_private_files(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=120)
        app.run()
        self.assertEqual(len(app.exception), 0, [error.message for error in app.exception])
        baseline = {metric.label: metric.value for metric in app.metric}
        self.assertIn('Pedidos con estado Back Order', baseline)
        self.assertIn('Con faltante bruto estimado', baseline)
        self.assertIn('Prioritarias por cobertura (<4 meses)', baseline)
        self.assertEqual(len(app.tabs), 5)
        self.assertEqual(len(app.get('file_uploader')), 0)
        self.assertTrue(any('Todos los códigos' in notice.value for notice in app.info))
        quality = [metric.value for metric in app.metric if metric.label.startswith('Comprobaciones')]

        forecast, demand, transits = make_demo_data()
        unique = forecast.item.notna() & ~forecast.item.duplicated(keep=False)
        expected = forecast.loc[unique & forecast.monthly_demand.gt(0)
                                & forecast.inventory.ge(0)
                                & (forecast.inventory / forecast.monthly_demand).lt(4)]
        priority_codes = set(expected.item)
        risk_codes = set(forecast.loc[unique & (forecast.monthly_demand * forecast.lead_time - forecast.inventory).gt(0), 'item'])

        def metric_counts(label):
            return [int(metric.value.replace(' códigos', '').replace(',', ''))
                    for metric in app.metric if metric.label == label]

        def check_priority_view(codes):
            self.assertEqual(len(app.exception), 0, [error.message for error in app.exception])
            self.assertEqual(metric_counts('Refacciones con código único'), [len(codes)])
            self.assertEqual(metric_counts('Prioritarias por cobertura (<4 meses)'), [len(codes)] * 2)
            actions = next(table.value for table in app.dataframe if 'Validación pendiente' in table.value)
            self.assertTrue(set(actions['Código']).issubset(codes))
            self.assertTrue(actions['Atención por cobertura'].eq(COVERAGE_PRIORITY_LABEL).all())
            # The visible demand and logistics totals must reflect the same item set.
            demand_view = next(table.value for table in app.dataframe if 'Estado de la orden' in table.value)
            shown_lines = sum(int(value.replace(',', '')) for value in demand_view['Líneas de orden'])
            self.assertEqual(shown_lines, int(demand.item.isin(codes).sum()))
            transit_view = next(table.value for table in app.dataframe if 'Piezas planeadas' in table.value)
            shown_units = sum(float(value.replace(' pzas', '').replace(',', '')) for value in transit_view['Piezas planeadas'])
            self.assertAlmostEqual(shown_units, transits.loc[transits.item.isin(codes), 'quantity'].sum(), places=2)
            self.assertEqual(quality, [metric.value for metric in app.metric if metric.label.startswith('Comprobaciones')])

        self.assertEqual(metric_counts('Prioritarias por cobertura (<4 meses)'), [len(priority_codes)] * 2)
        app.checkbox(key='only_low_coverage').set_value(True).run()
        check_priority_view(priority_codes)
        app.checkbox[0].set_value(True).run()
        check_priority_view(priority_codes & risk_codes)
        print(f'Cobertura <4: {len(priority_codes)} códigos; coincidencia con faltante bruto: {len(priority_codes & risk_codes)}. Demanda y logística verificadas por código.')

        # Clear family: every operational section must be empty, quality stays global.
        app.multiselect[0].set_value([]).run()
        self.assertEqual(len(app.exception), 0, [error.message for error in app.exception])
        self.assertEqual(next(metric.value for metric in app.metric if metric.label == 'Refacciones con código único'), '0 códigos')
        self.assertEqual(next(metric.value for metric in app.metric if metric.label == 'Pedidos con estado Back Order'), '0 piezas')
        self.assertEqual(metric_counts('Prioritarias por cobertura (<4 meses)'), [0, 0])
        self.assertEqual(quality, [metric.value for metric in app.metric if metric.label.startswith('Comprobaciones')])
        # Restore and apply risk: overview and inventory counts agree; other tabs run too.
        app.multiselect[0].set_value(app.multiselect[0].options)
        app.checkbox(key='only_low_coverage').set_value(False)
        app.checkbox[0].set_value(True).run()
        self.assertEqual(len(app.exception), 0, [error.message for error in app.exception])
        counts = [metric.value.replace(' códigos', '').replace(',', '') for metric in app.metric if metric.label == 'Con faltante bruto estimado']
        self.assertEqual(len(counts), 2)
        self.assertEqual(counts[0], counts[1])


if __name__ == '__main__':
    unittest.main()
