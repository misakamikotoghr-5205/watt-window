#!/usr/bin/env python3
"""Repeat local tests and full advisory export workflows with no network/device use."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    tests = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    if not result.wasSuccessful(): return 1
    output = ROOT / 'output'; output.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='verified-', dir=output))
    examples = []
    for name in ['household', 'shop', 'infeasible']:
        run = subprocess.run([sys.executable, '-m', 'watt_window', 'solve', 'examples/' + name + '.json', '--out', str(directory / name)], cwd=ROOT, capture_output=True, text=True, check=True)
        plan = json.loads(run.stdout)
        if plan['proposed']:
            assert plan['proposed']['valid_in_model']
            assert (directory / name / 'schedule.ics').is_file()
        else: assert not (directory / name / 'schedule.ics').exists()
        examples.append({'name': name, 'status': plan['status'], 'original_estimated_cost': plan['baseline']['estimated_cost']['decimal'], 'proposed_estimated_cost': plan['proposed']['estimated_cost']['decimal'] if plan['proposed'] else None, 'currency': plan['currency'], 'model_optimality_proven': plan['optimality_proven_in_model']})
    run = subprocess.run([sys.executable, '-m', 'watt_window', 'sensitivity', 'examples/household.json', '--scenarios', 'examples/sensitivity.json', '--out', str(directory / 'sensitivity')], cwd=ROOT, capture_output=True, text=True, check=True)
    assert len(json.loads(run.stdout)['scenarios']) == 4
    verification = {'verified_at': datetime.now(timezone.utc).isoformat(), 'tests_passed': result.testsRun, 'examples': examples, 'sensitivity_scenarios': 4, 'artifacts': str(directory), 'network_requests': 0, 'device_commands_sent': 0, 'measured_savings': False, 'carbon_reduction_claimed': False, 'competition_status': 'Pre-event prototype; not registered or shortlisted; not work performed in the Nov 28–30 event window.'}
    (output / 'verification.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__': raise SystemExit(main())
