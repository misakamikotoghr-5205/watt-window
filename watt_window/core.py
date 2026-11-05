"""Bounded branch-and-bound on an explicit finite grid; exact rational costs."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import hashlib
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class InputError(ValueError): pass


def fields(value, required, name):
    if not isinstance(value, dict) or set(value) != set(required): raise InputError(name + ' has missing or unknown fields')


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high: raise InputError(f'{name} must be an integer in {low}..{high}')
    return value


def text(value, name, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum: raise InputError(name + ' must be nonblank text')
    return value


def number(value, name, negative=False):
    if not isinstance(value, str) or not re.fullmatch(r'-?(?:0|[1-9]\d{0,3})(?:\.\d{1,3})?', value): raise InputError(name + ' must be a decimal string with up to three decimal places')
    parsed = Fraction(Decimal(value))
    if not negative and parsed <= 0: raise InputError(name + ' must be positive')
    return parsed


def instant(value):
    if not isinstance(value, str): raise InputError('start must be an ISO timestamp with an explicit offset')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None: raise InputError('start needs an explicit timezone offset')
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc: raise InputError('Invalid start timestamp') from exc


def decimal(value):
    with localcontext() as context:
        context.prec = 40
        return str((Decimal(value.numerator) / Decimal(value.denominator)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_EVEN))


def exact_cost(value): return {'decimal': decimal(value), 'numerator': value.numerator, 'denominator': value.denominator}


def validate(raw):
    fields(raw, {'schema_version', 'name', 'start', 'timezone', 'slot_minutes', 'currency', 'tariff_source', 'prices_per_kwh', 'capacity_watts', 'background_watts', 'jobs'}, 'problem')
    problem = deepcopy(raw)
    if type(problem['schema_version']) is not int or problem['schema_version'] != 1: raise InputError('Unsupported schema version')
    text(problem['name'], 'name', 160); start = instant(problem['start'])
    try: ZoneInfo(text(problem['timezone'], 'timezone', 100))
    except (ZoneInfoNotFoundError, ValueError) as exc: raise InputError('Unknown IANA timezone') from exc
    if problem['slot_minutes'] not in (15, 30, 60) or type(problem['slot_minutes']) is not int: raise InputError('slot_minutes must be 15, 30 or 60')
    if not isinstance(problem['currency'], str) or not re.fullmatch(r'[A-Z]{3}', problem['currency']): raise InputError('Use one three-letter currency code')
    text(problem['tariff_source'], 'tariff_source', 1000)
    if not isinstance(problem['prices_per_kwh'], list) or not 1 <= len(problem['prices_per_kwh']) <= 48: raise InputError('Provide 1–48 slot prices')
    for price in problem['prices_per_kwh']: number(price, 'price', negative=True)
    horizon = len(problem['prices_per_kwh'])
    try: start + timedelta(minutes=horizon * problem['slot_minutes'])
    except OverflowError as exc: raise InputError('Horizon exceeds datetime range') from exc
    integer(problem['capacity_watts'], 'capacity_watts', 1, 50000)
    if not isinstance(problem['background_watts'], list) or len(problem['background_watts']) != horizon: raise InputError('background_watts must have one value per price slot')
    for watts in problem['background_watts']: integer(watts, 'background watts', 0, 50000)
    if not isinstance(problem['jobs'], list) or not 1 <= len(problem['jobs']) <= 12: raise InputError('Provide 1–12 not-yet-started jobs')
    seen = set()
    for job in problem['jobs']:
        fields(job, {'id', 'name', 'earliest_start', 'latest_finish', 'duration_slots', 'power_watts', 'estimated_kwh', 'estimate_source', 'baseline_start', 'locked', 'noncritical_confirmed'}, 'job')
        if not isinstance(job['id'], str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', job['id']) or job['id'] in seen: raise InputError('Job IDs must be unique lowercase identifiers')
        seen.add(job['id']); text(job['name'], 'job name', 160); text(job['estimate_source'], 'estimate_source', 1000)
        if job['noncritical_confirmed'] is not True: raise InputError('Only explicitly confirmed noncritical jobs are supported')
        if type(job['locked']) is not bool: raise InputError('locked must be boolean')
        integer(job['earliest_start'], 'earliest_start', 0, horizon - 1)
        integer(job['latest_finish'], 'latest_finish', 1, horizon)
        integer(job['duration_slots'], 'duration_slots', 1, horizon)
        integer(job['baseline_start'], 'baseline_start', 0, horizon - job['duration_slots'])
        integer(job['power_watts'], 'power_watts', 1, 50000)
        energy = number(job['estimated_kwh'], 'estimated_kwh')
        upper = Fraction(job['power_watts'] * job['duration_slots'] * problem['slot_minutes'], 60000)
        if energy > upper: raise InputError('Estimated energy exceeds declared power × runtime; correct the inputs')
    return problem


def starts_for(job, problem):
    choices = [job['baseline_start']] if job['locked'] else range(job['earliest_start'], job['latest_finish'] - job['duration_slots'] + 1)
    return [start for start in choices if job['earliest_start'] <= start and start + job['duration_slots'] <= job['latest_finish'] and all(problem['background_watts'][slot] + job['power_watts'] <= problem['capacity_watts'] for slot in range(start, start + job['duration_slots']))]


def job_cost(job, start, problem):
    prices = problem['prices_per_kwh'][start:start + job['duration_slots']]
    return number(job['estimated_kwh'], 'estimated_kwh') * sum((number(price, 'price', True) for price in prices), Fraction()) / job['duration_slots']


def background_cost(problem):
    return sum((Fraction(watts * problem['slot_minutes'], 60000) * number(price, 'price', True) for watts, price in zip(problem['background_watts'], problem['prices_per_kwh'])), Fraction())


def evaluate(problem, schedule):
    profile = list(problem['background_watts']); violations = []; cost = background_cost(problem)
    if set(schedule) != {job['id'] for job in problem['jobs']}: raise InputError('Schedule must assign every job exactly once')
    for job in problem['jobs']:
        start = schedule[job['id']]
        integer(start, 'scheduled start', 0, len(profile) - job['duration_slots'])
        if not job['earliest_start'] <= start or start + job['duration_slots'] > job['latest_finish']: violations.append({'code': 'outside_window', 'job_id': job['id']})
        if job['locked'] and start != job['baseline_start']: violations.append({'code': 'locked_job_moved', 'job_id': job['id']})
        cost += job_cost(job, start, problem)
        for slot in range(start, start + job['duration_slots']): profile[slot] += job['power_watts']
    for slot, watts in enumerate(profile):
        if watts > problem['capacity_watts']: violations.append({'code': 'capacity_exceeded', 'slot': slot, 'watts': watts, 'limit': problem['capacity_watts']})
    return {'valid_in_model': not violations, 'violations': violations, 'estimated_cost': exact_cost(cost), 'power_profile_watts': profile, 'peak_watts': max(profile)}


def necessary_checks(problem, choices):
    reasons = []
    for job in problem['jobs']:
        if not choices[job['id']]: reasons.append({'code': 'no_single_job_fit', 'job_ids': [job['id']], 'detail': 'No start satisfies this job’s window, lock and background-plus-power limit.'})
    if reasons: return reasons
    for slot, watts in enumerate(problem['background_watts']):
        if watts > problem['capacity_watts']: return [{'code': 'background_over_limit', 'slot': slot, 'watts': watts, 'capacity_watts': problem['capacity_watts']}]
    endpoints = sorted({0, len(problem['prices_per_kwh'])} | {job['earliest_start'] for job in problem['jobs']} | {job['latest_finish'] for job in problem['jobs']})
    for left in endpoints:
        for right in endpoints:
            if right <= left: continue
            required, involved = 0, []
            for job in problem['jobs']:
                overlap = min(max(0, min(start + job['duration_slots'], right) - max(start, left)) for start in choices[job['id']])
                required += overlap * job['power_watts']
                if overlap: involved.append(job['id'])
            available = sum(problem['capacity_watts'] - watts for watts in problem['background_watts'][left:right])
            if required > available:
                return [{'code': 'window_power_demand', 'from_slot': left, 'to_slot_exclusive': right, 'job_ids': involved, 'required_watt_slots': required, 'available_watt_slots': available, 'detail': 'Even the minimum unavoidable occupancy exceeds the available watt-slots in this interval.'}]
    return []


def solve(raw, max_nodes=100000):
    problem = validate(raw); integer(max_nodes, 'max_nodes', 1, 1000000)
    baseline = {job['id']: job['baseline_start'] for job in problem['jobs']}; baseline_report = evaluate(problem, baseline)
    choices = {job['id']: starts_for(job, problem) for job in problem['jobs']}
    proofs = necessary_checks(problem, choices)
    base_cost = background_cost(problem)
    ordered = sorted(problem['jobs'], key=lambda job: (len(choices[job['id']]), -job['power_watts'] * job['duration_slots'], job['id']))
    costs = {job['id']: {start: job_cost(job, start, problem) for start in choices[job['id']]} for job in ordered}
    minima = [min(costs[job['id']].values()) if costs[job['id']] else Fraction() for job in ordered]
    suffix = [Fraction()] * (len(ordered) + 1)
    for index in range(len(ordered) - 1, -1, -1): suffix[index] = suffix[index + 1] + minima[index]
    best = deepcopy(baseline) if baseline_report['valid_in_model'] else None
    best_cost = sum((job_cost(job, baseline[job['id']], problem) for job in ordered), Fraction()) if best is not None else None
    profile = list(problem['background_watts']); assignment = {}; nodes = 0; exhausted = False
    def search(index, cost):
        nonlocal best, best_cost, nodes, exhausted
        if best_cost is not None and cost + suffix[index] >= best_cost: return
        if nodes >= max_nodes: exhausted = True; return
        nodes += 1
        if index == len(ordered): best = deepcopy(assignment); best_cost = cost; return
        job = ordered[index]
        for start in sorted(choices[job['id']], key=lambda value: (costs[job['id']][value], value)):
            active = range(start, start + job['duration_slots'])
            if any(profile[slot] + job['power_watts'] > problem['capacity_watts'] for slot in active): continue
            for slot in active: profile[slot] += job['power_watts']
            assignment[job['id']] = start
            search(index + 1, cost + costs[job['id']][start])
            for slot in active: profile[slot] -= job['power_watts']
            assignment.pop(job['id'])
            if exhausted: break
    if not proofs: search(0, Fraction())
    if proofs: best = None; best_cost = None
    proven = not exhausted or (best_cost is not None and best_cost == suffix[0])
    status = 'infeasible' if proofs or (best is None and not exhausted) else 'budget_exhausted_no_plan' if best is None else 'optimal_in_model' if proven else 'feasible_not_proven_optimal'
    proposed = evaluate(problem, best) if best is not None else None
    if proposed and not proposed['valid_in_model']: raise RuntimeError('Internal schedule validation failed')
    if best is None and not proofs: proofs = [{'code': 'search_budget_exhausted' if exhausted else 'no_grid_assignment', 'detail': 'No feasible plan found within the budget; infeasibility is not proven.' if exhausted else 'Complete search found no assignment satisfying all windows and the modeled power limit.'}]
    start_time = instant(problem['start']); zone = ZoneInfo(problem['timezone'])
    scheduled = []
    if best is not None:
        for job in sorted(problem['jobs'], key=lambda job: (best[job['id']], job['id'])):
            begin = start_time + timedelta(minutes=best[job['id']] * problem['slot_minutes']); end = begin + timedelta(minutes=job['duration_slots'] * problem['slot_minutes'])
            scheduled.append({'id': job['id'], 'name': job['name'], 'start_slot': best[job['id']], 'end_slot_exclusive': best[job['id']] + job['duration_slots'], 'start': begin.isoformat(), 'end': end.isoformat(), 'local_start': begin.astimezone(zone).isoformat(), 'local_end': end.astimezone(zone).isoformat(), 'power_watts': job['power_watts'], 'estimated_kwh': job['estimated_kwh'], 'estimated_cost': exact_cost(job_cost(job, best[job['id']], problem)), 'baseline_start_slot': job['baseline_start'], 'estimate_source': job['estimate_source']})
    encoded = json.dumps(problem, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    delta = Fraction(baseline_report['estimated_cost']['numerator'], baseline_report['estimated_cost']['denominator']) - (base_cost + best_cost) if best_cost is not None else None
    return {'schema_version': 1, 'problem_sha256': hashlib.sha256(encoded).hexdigest(), 'name': problem['name'], 'currency': problem['currency'], 'timezone': problem['timezone'], 'start': problem['start'], 'slot_minutes': problem['slot_minutes'], 'capacity_watts': problem['capacity_watts'], 'tariff_source': problem['tariff_source'],
            'status': status, 'optimality_proven_in_model': best is not None and proven, 'infeasibility_proven_in_model': status == 'infeasible', 'budget_exhausted': exhausted, 'nodes_visited': nodes, 'node_budget': max_nodes,
            'independent_cost_lower_bound': None if proofs else exact_cost(base_cost + suffix[0]), 'diagnostics': proofs,
            'schedule': scheduled, 'proposed': proposed, 'baseline': baseline_report, 'estimated_cost_delta_from_baseline': exact_cost(delta) if delta is not None else None,
            'baseline_is_valid_comparator': baseline_report['valid_in_model'], 'device_commands_sent': 0, 'measured_savings': False, 'carbon_reduction_claimed': False,
            'assumptions': ['Only explicitly user-confirmed noncritical, not-yet-started jobs; each runs contiguously.', 'User-entered power and background are concurrent capacity estimates, not electrical safety validation.', 'Estimated energy is spread uniformly across active slots; tariff values are user inputs in one currency.', 'Optimality refers only to this finite grid and supplied model. No equipment is controlled and no real saving or carbon reduction is measured.']}


def sensitivity(raw, scenarios, max_nodes=100000):
    problem = validate(raw)
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 8: raise InputError('Provide 1–8 explicit sensitivity scenarios')
    results, seen = [], set()
    for scenario in scenarios:
        fields(scenario, {'id', 'capacity_watts', 'prices_per_kwh'}, 'scenario')
        if not isinstance(scenario['id'], str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', scenario['id']) or scenario['id'] in seen: raise InputError('Scenario IDs must be unique lowercase identifiers')
        seen.add(scenario['id']); changed = deepcopy(problem)
        changed['capacity_watts'] = scenario['capacity_watts']; changed['prices_per_kwh'] = scenario['prices_per_kwh']
        changed['tariff_source'] = 'User-supplied hypothetical tariff in sensitivity scenario ' + scenario['id']
        if not isinstance(changed['prices_per_kwh'], list) or len(changed['prices_per_kwh']) != len(problem['prices_per_kwh']): raise InputError('Scenario must preserve the time grid')
        result = solve(changed, max_nodes)
        results.append({'scenario_id': scenario['id'], 'capacity_watts': changed['capacity_watts'], 'prices_per_kwh': changed['prices_per_kwh'], 'result': result})
    return {'assumptions_only': True, 'baseline_tariff_source': problem['tariff_source'], 'device_commands_sent': 0, 'note': 'Each scenario is independently solved with its own entered tariff/capacity. Costs across different tariffs are not causal measured savings.', 'scenarios': results}
