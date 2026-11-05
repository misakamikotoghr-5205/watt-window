import csv
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from watt_window.core import InputError, solve
from watt_window.export import calendar, export_bundle, report
from watt_window.__main__ import load
from test_solver import ROOT, example


class WorkflowTests(unittest.TestCase):
    def test_real_cli_exports_a_complete_plan_and_sensitivity(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'plan'
            completed = subprocess.run([sys.executable, '-m', 'watt_window', 'solve', 'examples/household.json', '--out', str(target)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result['status'], 'optimal_in_model')
            self.assertTrue(all((target / name).is_file() for name in ['result.json', 'report.html', 'schedule.ics', 'schedule.csv']))
            second = subprocess.run([sys.executable, '-m', 'watt_window', 'sensitivity', 'examples/household.json', '--scenarios', 'examples/sensitivity.json', '--out', str(Path(directory) / 'sensitivity')], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(len(json.loads(second.stdout)['scenarios']), 4)
            self.assertIn('cheap_window_disappears', (Path(directory) / 'sensitivity/report.html').read_text())
            again = subprocess.run([sys.executable, '-m', 'watt_window', 'solve', 'examples/household.json', '--out', str(target)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(again.returncode, 2)

    def test_infeasible_output_has_no_actionable_calendar_or_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'infeasible'; export_bundle(solve(example('infeasible')), target)
            self.assertTrue((target / 'report.html').exists())
            self.assertFalse((target / 'schedule.ics').exists())
            self.assertFalse((target / 'schedule.csv').exists())
        with self.assertRaises(InputError): calendar(solve(example('infeasible')))

    def test_calendar_utf8_folding_and_text_injection_do_not_create_extra_events(self):
        data = example(); data['jobs'][0]['name'] = '洗碗任务' * 30 + '\nBEGIN:VEVENT'
        result = solve(data); encoded = calendar(result)
        self.assertTrue(all(len(line.encode()) <= 75 for line in encoded.split('\r\n')))
        self.assertEqual(encoded.count('\r\nBEGIN:VEVENT\r\n'), len(result['schedule']))
        self.assertIn('\\nBEGIN:VEVENT', encoded)

    def test_html_escapes_names_and_csv_neutralizes_formula_names(self):
        data = example(); data['jobs'][0]['name'] = '=HYPERLINK("https://invalid.test") <script>alert(1)</script>'
        result = solve(data)
        self.assertNotIn('<script>', report(result))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'safe'; export_bundle(result, target)
            rows = list(csv.DictReader(StringIO((target / 'schedule.csv').read_text())))
            self.assertTrue(next(row['name'] for row in rows if row['job_id'] == data['jobs'][0]['id']).startswith("'="))

    def test_json_duplicates_nonfinite_and_oversized_inputs_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.json'
            for content in [b'{"x":1,"x":2}', b'{"x":NaN}', b'0' * 200001]:
                path.write_bytes(content)
                with self.assertRaises(InputError): load(path)


if __name__ == '__main__': unittest.main()
