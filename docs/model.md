# Finite-grid model and schema

See [the full household example](../examples/household.json). Objects require exactly the listed fields; quantities are not inferred from appliance names.

| Problem field | Type / interpretation |
|---|---|
| `schema_version` | `1` |
| `name` | Nonblank label |
| `start`, `timezone` | ISO timestamp with offset; IANA display timezone |
| `slot_minutes` | 15, 30 or 60 real elapsed minutes |
| `currency` | One three-letter code for all supplied prices |
| `tariff_source` | User-provided source/assumption note |
| `prices_per_kwh` | 1–48 decimal strings; negative tariffs allowed |
| `capacity_watts` | Positive integer concurrent limit for the modeled total |
| `background_watts` | One nonnegative estimate per slot, included in the limit and cost |
| `jobs` | 1–12 noncritical jobs that have not started |

Each job requires `id`, `name`, `earliest_start` (inclusive), `latest_finish` (exclusive), `duration_slots`, `power_watts`, `estimated_kwh`, `estimate_source`, `baseline_start`, `locked` and `noncritical_confirmed:true`. IDs are unique lowercase identifiers. Start indices refer to the common grid. The original start must fit inside the overall horizon but may violate the proposed window, in which case the baseline is explicitly invalid. A locked job retains its original start; if that conflicts with a window, no silent override occurs.

Watts and slot counts are bounded integers; energy/price strings have up to three decimal places. Estimated energy must be positive and no larger than declared watts × runtime. This consistency check does not verify the physical measurement. Jobs are non-preemptive: a two-slot job cannot split itself across separated cheap slots.

For a job with energy estimate E and duration d, each active slot is modeled as E/d kWh, with cost E/d × sum(active-slot prices). Background energy is watts × slot-hours / 1000. Concurrent capacity uses declared job watts plus the per-slot background estimate. Energy and peak power are distinct inputs; cost assumes uniform energy, while capacity uses the declared concurrent power envelope.

The solver enumerates integer starts satisfying windows/locks and individual background-plus-job capacity. It orders constrained jobs first and prunes using a sum of independent cheapest-start costs, which is an admissible lower bound even with negative prices. Only exact rational values drive pruning. A valid original plan is an initial incumbent; no plan is returned without full model validation.

Before search, necessary checks can prove contradictions: a job has no allowed start, fixed background exceeds capacity, or an interval has more minimum unavoidable job watt-slots than the available capacity after background. This interval bound is necessary, not a claim that passing it proves feasibility. Otherwise, complete search or an achieved objective lower bound is needed to prove optimality. Budget exhaustion never alone proves infeasibility.

Output includes exact cost ratios, rounded display strings, original and proposed profiles, constraints, source notes, input SHA256, proof flags, node counts and zero device commands. A checksum identifies input content, not authorship. Equal-cost schedules may preserve the original incumbent; the objective does not optimize comfort, fairness, wear or earliest finish.

Sensitivity input is a list of 1–8 `{id,capacity_watts,prices_per_kwh}` objects. The time grid/jobs remain fixed and each scenario is independently solved. All changed tariffs are labeled hypothetical; the original source note is retained separately. Runtime complexity grows with jobs/windows. The budget is deterministic search nodes, not a wall-clock limit; bounded validation and interval checks run before it.

UTC instants define elapsed slots, then the chosen timezone formats local display, including explicit offsets at daylight-saving changes. Calendar events use UTC and require manual import. No real-time scheduler, background process or actuator exists.
