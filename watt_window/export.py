"""Static advisory artifacts, never device or calendar API calls."""
from datetime import datetime, timezone
from html import escape
import csv
import json
from pathlib import Path

from .core import InputError


def calendar_text(value):
    return str(value).replace('\\', '\\\\').replace('\r', '').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')


def folded(line):
    # RFC 5545 limits folded physical lines to 75 octets, not 75 characters.
    rows, current = [], ''
    for character in line:
        if len((current + character).encode('utf-8')) > 75:
            rows.append(current); current = ' ' + character
        else: current += character
    return '\r\n'.join(rows + [current])


def calendar(result):
    if result['proposed'] is None: raise InputError('No feasible plan exists to export to calendar')
    rows = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Watt Window//Advisory Prototype//EN', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH']
    now = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for job in result['schedule']:
        begin = datetime.fromisoformat(job['start']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        end = datetime.fromisoformat(job['end']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        rows += ['BEGIN:VEVENT', 'UID:' + result['problem_sha256'][:24] + '-' + job['id'] + '@watt-window.local', 'DTSTAMP:' + now, 'DTSTART:' + begin, 'DTEND:' + end, 'SUMMARY:' + calendar_text('Advisory: ' + job['name']), 'DESCRIPTION:' + calendar_text('User-estimated schedule only. No equipment is controlled. Review actual device requirements and conditions yourself.'), 'END:VEVENT']
    return '\r\n'.join(folded(row) for row in rows + ['END:VCALENDAR']) + '\r\n'


def report(result):
    e = escape
    rows = ''.join('<tr><td>' + e(job['name']) + '</td><td>' + e(job['local_start']) + '</td><td>' + e(job['local_end']) + '</td><td>' + str(job['power_watts']) + '</td><td>' + e(job['estimated_kwh']) + '</td><td>' + e(job['estimated_cost']['decimal']) + '</td></tr>' for job in result['schedule'])
    before = result['baseline']['estimated_cost']['decimal']; after = result['proposed']['estimated_cost']['decimal'] if result['proposed'] else 'No feasible plan found'
    delta = result['estimated_cost_delta_from_baseline']['decimal'] if result['estimated_cost_delta_from_baseline'] else '—'
    heights = result['proposed']['power_profile_watts'] if result['proposed'] else result['baseline']['power_profile_watts']
    bars = ''.join(f'<rect x="{index*32+55}" y="{180-min(150, watts*150/max(max(heights),result["capacity_watts"])):.2f}" width="23" height="{min(150, watts*150/max(max(heights),result["capacity_watts"])):.2f}" fill="{"#bd392f" if watts>result["capacity_watts"] else "#278574"}"/><text x="{index*32+55}" y="201" font-size="10">{index}</text>' for index, watts in enumerate(heights))
    capacity_y = 180 - result['capacity_watts'] * 150 / max(max(heights), result['capacity_watts'])
    svg = f'<svg role="img" aria-label="Modeled concurrent watts by slot; red dashed line is capacity" viewBox="0 0 {len(heights)*32+100} 220"><title>Modeled concurrent watts per slot</title>{bars}<line x1="45" x2="{len(heights)*32+70}" y1="{capacity_y:.2f}" y2="{capacity_y:.2f}" stroke="#bd392f" stroke-dasharray="5 4"/><text x="45" y="18" font-size="12">Capacity {result["capacity_watts"]} W; peak {max(heights)} W</text></svg>'
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Watt Window — {e(result['name'])}</title><style>
body{{background:#f1f5f2;color:#18332e;font:16px/1.6 system-ui,sans-serif;margin:0}}main{{max-width:1100px;padding:28px 20px;margin:auto}}header{{background:#123d34;color:white;padding:28px;border-radius:18px}}h1{{margin:0;font-size:34px}}section{{background:white;border:1px solid #d5e2dc;border-radius:12px;padding:22px;margin:20px 0}}h2{{font-size:21px}}.cards{{display:flex;flex-wrap:wrap;gap:18px}}.cards p{{padding:14px;background:#edf5f1;border-radius:10px}}strong{{font-size:22px}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #d5e2dc;overflow-wrap:anywhere}}.scroll{{overflow-x:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}svg{{max-height:260px;width:100%}}code{{overflow-wrap:anywhere}}@media(max-width:650px){{main{{padding:16px 12px}}header{{padding:20px}}h1{{font-size:27px}}}}</style><main><header><h1>Watt Window</h1><p>{e(result['name'])}</p><p>Advisory finite-grid schedule · no connected devices · estimates only</p></header>
<section><h2>{e(result['status'].replace('_',' '))}</h2><p>Visited {result['nodes_visited']} / {result['node_budget']} search nodes. Optimality proven in the supplied model: {str(result['optimality_proven_in_model']).lower()}.</p><div class="cards"><p>Original estimate<br><strong>{e(before)}</strong> {e(result['currency'])}</p><p>Proposed estimate<br><strong>{e(after)}</strong> {e(result['currency'])}</p><p>Estimated difference<br><strong>{e(delta)}</strong> {e(result['currency'])}</p></div><p>Original plan satisfies modeled constraints: {str(result['baseline_is_valid_comparator']).lower()}. If false, a cost difference is not a like-for-like saving.</p><p>{e(result['tariff_source'])}</p></section>
<section><h2>Concurrent power by slot</h2><p>Showing {'the proposed plan' if result['proposed'] else 'the original plan because no feasible proposal was found'}.</p>{svg}<p>Profile: {e(', '.join(map(str,heights)))} W. These are user-entered power/background estimates, not a safety test or measured demand.</p></section>
<section><h2>Proposed noncritical jobs</h2><div class="scroll"><table><thead><tr><th>Job</th><th>Start ({e(result['timezone'])})</th><th>End</th><th>Power W</th><th>Est. kWh</th><th>Est. cost</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section><h2>Why a plan may be unavailable</h2><pre>{e(json.dumps(result['diagnostics'],ensure_ascii=False,indent=2))}</pre><h2>Original-plan violations</h2><pre>{e(json.dumps(result['baseline']['violations'],ensure_ascii=False,indent=2))}</pre></section>
<section><h2>Interpretation</h2><ul>{''.join('<li>'+e(note)+'</li>' for note in result['assumptions'])}</ul><p>Device commands sent: 0. No measured savings or carbon reduction claimed.</p><p>Input SHA256: <code>{result['problem_sha256']}</code></p></section></main></html>'''


def export_bundle(result, destination):
    target = Path(destination)
    if target.exists(): raise InputError('Output directory exists; choose a new path to preserve the earlier plan')
    target.mkdir(parents=True)
    (target / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    (target / 'report.html').write_text(report(result))
    if result['proposed']:
        (target / 'schedule.ics').write_bytes(calendar(result).encode('utf-8'))
        with (target / 'schedule.csv').open('w', newline='') as output:
            writer = csv.writer(output); writer.writerow(['job_id', 'name', 'start', 'end', 'power_watts', 'estimated_kwh', 'estimated_cost', 'currency'])
            for job in result['schedule']:
                name = job['name']; name = "'" + name if name[:1] in '=+-@\t\r' else name
                writer.writerow([job['id'], name, job['local_start'], job['local_end'], job['power_watts'], job['estimated_kwh'], job['estimated_cost']['decimal'], result['currency']])
    return str(target.resolve())


def export_sensitivity(result, destination):
    target = Path(destination)
    if target.exists(): raise InputError('Output directory exists; choose a new path')
    target.mkdir(parents=True)
    (target / 'sensitivity.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    rows = []
    for scenario in result['scenarios']:
        plan = scenario['result']
        cost = plan['proposed']['estimated_cost']['decimal'] if plan['proposed'] else 'No plan'
        rows.append('<tr>' + ''.join('<td>' + escape(str(value)) + '</td>' for value in [scenario['scenario_id'], scenario['capacity_watts'], plan['status'], cost, plan['baseline']['estimated_cost']['decimal'], plan['optimality_proven_in_model']]) + '</tr>')
    body = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Watt Window sensitivity</title><style>body{font:16px/1.6 system-ui;background:#f1f5f2;color:#18332e;padding:24px}main{max-width:1100px;margin:auto;background:white;border-radius:16px;padding:24px}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:12px;border-bottom:1px solid #cbded4}.scroll{overflow-x:auto}</style><main><h1>Watt Window: sensitivity</h1><p>' + escape(result['note']) + '</p><div class="scroll"><table><thead><tr><th>Scenario</th><th>Capacity W</th><th>Status</th><th>Proposed est. cost</th><th>Original est. cost</th><th>Model optimality proven</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div><p>All values use the same entered currency. Inspect sensitivity.json for each scenario’s tariff, complete allocation and source assumptions. No device commands or measured savings.</p></main></html>'
    (target / 'report.html').write_text(body)
    return str(target.resolve())
