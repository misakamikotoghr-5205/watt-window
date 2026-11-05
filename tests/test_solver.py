from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import itertools
import json
from pathlib import Path
import random
import unittest

from watt_window.core import InputError, evaluate, sensitivity, solve, validate

ROOT = Path(__file__).resolve().parents[1]


def example(name='household'):
    return json.loads((ROOT / 'examples' / (name + '.json')).read_text())


def small(prices=('1', '0', '1'), baseline=(0, 2)):
    data = example(); data['prices_per_kwh'] = list(prices); data['background_watts'] = [0] * len(prices); data['capacity_watts'] = 1000
    data['jobs'] = data['jobs'][:2]
    for job, start in zip(data['jobs'], baseline):
        job.update(earliest_start=0, latest_finish=len(prices), duration_slots=1, power_watts=1000, estimated_kwh='0.5', baseline_start=start)
    return data


def cost_value(value): return Fraction(value['numerator'], value['denominator'])


class SolverTests(unittest.TestCase):
    def test_complete_household_plan_has_lower_estimate_and_respects_every_constraint(self):
        data = example(); before = deepcopy(data); result = solve(data)
        self.assertEqual(data, before)
        self.assertEqual(result['status'], 'optimal_in_model')
        self.assertTrue(result['baseline_is_valid_comparator'])
        self.assertGreater(cost_value(result['estimated_cost_delta_from_baseline']), 0)
        schedule = {job['id']: job['start_slot'] for job in result['schedule']}
        self.assertTrue(evaluate(validate(data), schedule)['valid_in_model'])
        self.assertLessEqual(max(result['proposed']['power_profile_watts']), data['capacity_watts'])
        self.assertEqual(result['device_commands_sent'], 0)
        self.assertFalse(result['carbon_reduction_claimed'])

    def test_fixed_job_is_not_moved_to_cheaper_slots(self):
        result = solve(example('shop'))
        self.assertEqual(next(job['start_slot'] for job in result['schedule'] if job['id'] == 'sign_test'), 0)

    def test_window_overload_is_proved_with_a_checkable_necessary_bound(self):
        result = solve(example('infeasible'), 1)
        self.assertEqual(result['status'], 'infeasible')
        self.assertTrue(result['infeasibility_proven_in_model'])
        proof = result['diagnostics'][0]
        self.assertEqual(proof['code'], 'window_power_demand')
        self.assertGreater(proof['required_watt_slots'], proof['available_watt_slots'])
        self.assertEqual(result['schedule'], [])
        self.assertIsNone(result['proposed'])

    def test_job_power_and_missing_start_window_are_not_silently_relaxed(self):
        for mutate in (lambda data: data.update(capacity_watts=500), lambda data: data['jobs'][0].update(earliest_start=10, latest_finish=11)):
            data = example(); mutate(data); result = solve(data)
            self.assertEqual(result['status'], 'infeasible')
            self.assertEqual(result['diagnostics'][0]['code'], 'no_single_job_fit')

    def test_budget_limit_preserves_valid_incumbent_without_claiming_optimality(self):
        result = solve(small(), 1)
        self.assertEqual(result['status'], 'feasible_not_proven_optimal')
        self.assertTrue(result['budget_exhausted'])
        self.assertFalse(result['optimality_proven_in_model'])
        self.assertTrue(result['proposed']['valid_in_model'])

    def test_no_plan_found_in_budget_does_not_mean_proven_infeasible(self):
        result = solve(small(baseline=(0, 0)), 1)
        self.assertEqual(result['status'], 'budget_exhausted_no_plan')
        self.assertFalse(result['infeasibility_proven_in_model'])
        self.assertIsNone(result['proposed'])

    def test_negative_tariffs_and_decimal_energy_use_exact_rational_objective(self):
        data = small(prices=('-0.333', '0.111', '0.222'))
        result = solve(data)
        self.assertEqual(cost_value(result['proposed']['estimated_cost']), Fraction(-111, 1000))
        self.assertTrue(result['optimality_proven_in_model'])

    def test_branch_and_bound_matches_an_independent_bruteforce_oracle(self):
        rng = random.Random(824)
        for _ in range(24):
            data = small(prices=[str(rng.randrange(-3, 8) / 10) for _ in range(4)])
            data['capacity_watts'] = rng.choice([1000, 2000]); data['background_watts'] = [rng.choice([0, 200]) for _ in range(4)]
            for job in data['jobs']:
                job['earliest_start'] = rng.randrange(0, 3); job['latest_finish'] = rng.randrange(job['earliest_start'] + 1, 5)
            oracle = []
            # Enumerate directly from the raw grid, without solver candidate,
            # cost, pruning, or schedule-evaluation helpers.
            for assignments in itertools.product(range(4), repeat=2):
                watts = list(data['background_watts']); valid = True; cost = Fraction()
                for job, start in zip(data['jobs'], assignments):
                    if not job['earliest_start'] <= start < job['latest_finish']: valid = False
                    watts[start] += job['power_watts']
                    cost += Fraction(Decimal(job['estimated_kwh'])) * Fraction(Decimal(data['prices_per_kwh'][start]))
                if valid and max(watts) <= data['capacity_watts']:
                    cost += sum((Fraction(w * 30, 60000) * Fraction(Decimal(p)) for w, p in zip(data['background_watts'], data['prices_per_kwh'])), Fraction())
                    oracle.append(cost)
            result = solve(data)
            if oracle:
                self.assertEqual(cost_value(result['proposed']['estimated_cost']), min(oracle))
                self.assertTrue(result['optimality_proven_in_model'])
            else: self.assertEqual(result['status'], 'infeasible')

    def test_invalid_original_plan_is_retained_and_not_presented_as_valid_saving(self):
        data = small(baseline=(0, 0)); result = solve(data)
        self.assertFalse(result['baseline_is_valid_comparator'])
        self.assertTrue(any(issue['code'] == 'capacity_exceeded' for issue in result['baseline']['violations']))
        self.assertTrue(result['proposed']['valid_in_model'])

    def test_contiguous_job_cannot_split_itself_across_disjoint_cheap_slots(self):
        data = small(prices=('0', '1', '0')); data['jobs'] = data['jobs'][:1]
        data['jobs'][0].update(duration_slots=2, estimated_kwh='1', baseline_start=0)
        result = solve(data)
        self.assertEqual(cost_value(result['proposed']['estimated_cost']), Fraction(1, 2))
        self.assertEqual(result['schedule'][0]['end_slot_exclusive'] - result['schedule'][0]['start_slot'], 2)

    def test_sensitivity_keeps_independent_assumptions_and_does_not_mutate_original(self):
        data = example(); before = deepcopy(data)
        scenarios = json.loads((ROOT / 'examples/sensitivity.json').read_text())
        result = sensitivity(data, scenarios)
        self.assertEqual(data, before)
        self.assertEqual(len(result['scenarios']), 4)
        self.assertEqual(result['scenarios'][0]['result']['proposed']['estimated_cost'], solve(data)['proposed']['estimated_cost'])
        self.assertIn('hypothetical', result['scenarios'][3]['result']['tariff_source'])

    def test_boolean_float_energy_and_critical_load_inputs_rejected(self):
        mutations = [lambda p: p.update(capacity_watts=True), lambda p: p['jobs'][0].update(noncritical_confirmed=False), lambda p: p['jobs'][0].update(estimated_kwh='9999'), lambda p: p['prices_per_kwh'].__setitem__(0, 0.5), lambda p: p.update(start='2026-11-28T18:00:00'), lambda p: p['jobs'][0].update(power_watts=1.5)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = example(); mutate(data)
                with self.assertRaises(InputError): solve(data)


if __name__ == '__main__': unittest.main()
