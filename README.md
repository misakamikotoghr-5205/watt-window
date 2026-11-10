# Watt Window

A small, explainable **advisory** scheduler for user-confirmed noncritical household or shop loads. Enter time windows, a tariff table, estimated energy, concurrent power and background load. Compare a proposed schedule against the original plan, inspect infeasibility, and test alternative assumptions.

Python 3.11+ standard library only, with system IANA timezone data. No network access, paid APIs, equipment control or AI inference. This is a **pre-event prototype** for Next Horizon 2026, not work performed during its future 48-hour event. The participant reports that the concept form was submitted; an independent receipt, shortlisting and final event submission remain unverified.

## Run

From this directory:

```sh
python3 -m watt_window solve examples/household.json --out output/my-household-plan
python3 -m watt_window solve examples/shop.json --out output/my-shop-plan
python3 -m watt_window solve examples/infeasible.json --out output/my-infeasible-plan
python3 -m watt_window sensitivity examples/household.json \
  --scenarios examples/sensitivity.json --out output/my-sensitivity
python3 scripts/verify.py
```

Each new plan directory contains `result.json` and a self-contained `report.html`. A feasible plan also includes `schedule.csv` and `schedule.ics` for manual review/import; no calendar or appliance API is contacted. Choose a new output path each run: previous plan directories are preserved. Sensitivity exports a compact HTML comparison and full per-scenario JSON.

The household example moves three fictional noncritical jobs among 12 half-hour slots. The shop example includes a fixed-time job. The infeasible example has more unavoidable workload in a short interval than the declared capacity can accommodate. Prices, energy estimates and backgrounds are **fictional user inputs**, not current utility quotes or smart-meter measurements.

## What the result establishes

The objective minimizes estimated energy cost on the supplied grid. Jobs are contiguous and not already running. Start/finish windows, locked starts, background load and concurrent watt limits are explicit. Per-job estimated energy is distributed uniformly over its active slots; declared power is used for concurrent capacity. Background cost is included in both plans. Fraction arithmetic keeps cost comparisons exact, including negative tariffs; displayed currency values round to six decimal places, with exact numerator/denominator retained in JSON.

The original plan is evaluated rather than assumed valid. If it violates a window or capacity, its estimate remains visible and `baseline_is_valid_comparator` is false. An estimated cost difference against an invalid baseline is not a like-for-like saving.

Search uses branch-and-bound with an independent per-job cost lower bound. The node budget defaults to 100,000 (maximum 1,000,000). Inspect the status:

| Status | Meaning |
|---|---|
| `optimal_in_model` | A feasible solution and an optimality proof for this finite input model |
| `feasible_not_proven_optimal` | A valid plan, but budget prevented an optimality proof |
| `budget_exhausted_no_plan` | No plan found within budget; infeasibility is **not** proven |
| `infeasible` | A necessary capacity/window contradiction or complete finite-grid search proves no plan fits |

Use `--max-nodes 1` to see budget limits without disguising them as an infeasible result. A valid original plan may survive as an incumbent, clearly unproven optimal. Infeasible/no-plan results export no actionable calendar.

Necessary interval explanations show affected jobs, the slot interval, unavoidable watt-slots and available watt-slots. A job with no permissible start gets a separate explanation. These are mathematical input-model checks. User-entered watt values do not validate circuits, device start-up surges, unattended operation or equipment safety. The program does not schedule critical/medical/refrigeration loads; every supported job requires `noncritical_confirmed:true`.

No real cost saving or carbon reduction is measured or claimed. There is no carbon-intensity input, grid forecast, battery/PV model, thermal model or device controller. Users must assess actual equipment constraints before choosing what to do.

## Sensitivity and inputs

`examples/sensitivity.json` compares unchanged assumptions, tighter/more generous capacity and a changed cheap tariff window. Each scenario gets its own full solve, proof/budget status and hypothetical source note. Cross-tariff cost differences are not measured causal savings.

Input bounds: 1–48 slots at 15/30/60 minutes, 1–12 jobs, one currency, integers for watts/slot indices, decimal **strings** for prices and energy. Every job has a source note for its estimate; tariffs have their own source note. JSON rejects duplicate fields, nonfinite values, unknown fields and oversized input. Exact schema and model assumptions are in [docs/model.md](docs/model.md).

## Verification, comparisons and event status

`python3 scripts/verify.py` runs 17 local tests and complete CLI exports for all three examples plus four sensitivity cases. Tests include an independent brute-force oracle over randomized small grids, budget status, negative-price arithmetic, non-splittable jobs, locked starts, invalid baselines, infeasibility bounds, HTML/CSV/calendar escaping and actual CLI use. Output is in ignored `output/verification.json`. No remote service or device is needed; no CI claim is made.

Energy scheduling already has mature implementations. [docs/landscape.md](docs/landscape.md) compares EMHASS (MIT) and FlexMeasures (Apache-2.0), pinned to reviewed commits. This project is a narrower, independently implemented explanation-first prototype; no upstream code, assets or tests were copied.

Next Horizon's first stage requires a presentation; a software repository alone is not an entry. Dates, pending shortlisting and the remaining deliverables are recorded in [docs/competition.md](docs/competition.md). A truthful five-part [pitch outline](docs/pitch-outline.md) is included. The participant-reported concept submission is preserved without repeating it; slide/video attachments, shortlisting and any final live pitch are not established by this repository. The optional prototype video below is newly prepared material.

Original code and fictional examples: MIT, [LICENSE](LICENSE).

## Optional demonstration, November 10

2026年11月10日已完成[210秒可选原型演示](docs/media/watt-window-optional-prototype-demo.mp4)：从实际本地CLI输出制作英文静音证据卡，展示虚构输入下的排程、成本、功率、不可行解释、预算限制与敏感性。全程标注pre-event prototype/fictional fixture，既不是浏览器录屏，也不代表实测节省、设备控制或11月28–30日赛期工作。[媒体与QA记录](docs/evidence/local-demo-20261110.json)保留命令、哈希及14个实际MP4帧的检查范围；视频发布/赛事交件阶段另行核验。
