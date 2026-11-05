# Existing energy schedulers and this prototype

Checked 2026-11-05. Both projects' README and complete licenses were read at fixed public commits. [Source metadata](landscape-sources.json) records commit dates, URLs and original-file SHA256 hashes. We did not copy their code, fixtures, tests, UI or documentation.

| Existing project | What already exists | Watt Window's narrower choice |
|---|---|---|
| **EMHASS**, [`2306a87445e939bbc3350240d9467af4dd108751` README](https://github.com/davidusb-geek/emhass/blob/2306a87445e939bbc3350240d9467af4dd108751/README.md), 2026-11-04; [MIT license](https://github.com/davidusb-geek/emhass/blob/2306a87445e939bbc3350240d9467af4dd108751/LICENSE) | Residential optimization using linear programming, including electricity prices, solar generation, storage and Home Assistant integration. Shifting home energy use for cost is an established idea. | An entirely offline advisory artifact for a few noncritical jobs, with no Home Assistant requirement or controls. Explicit baseline violations, limited-search proof status, checkable interval contradictions and assumption comparison are the working prototype's focus. |
| **FlexMeasures**, [`8a1f5087496d82794bb262ecdb7ba6eec280a03f` README](https://github.com/FlexMeasures/flexmeasures/blob/8a1f5087496d82794bb262ecdb7ba6eec280a03f/README.md), 2026-11-04; [Apache-2.0 license](https://github.com/FlexMeasures/flexmeasures/blob/8a1f5087496d82794bb262ecdb7ba6eec280a03f/LICENSE) | Energy scheduling/optimization for multiple assets and commodities, with time-series data, forecasting, API/UI, plugins and uncertainty-aware data modeling. Inspectable energy modeling is not novel. | A small finite-grid model using only Python's standard library and exact rational cost comparisons. Input notes and JSON/HTML/CSV/ICS make a manually entered example easy to reproduce. It omits real-time forecasting, multi-tenancy, storage/PV/thermal models and integrations. |

## Borrowing and license boundary

These are design comparisons, not a claim that upstream products lack equivalent explanations or features. They are more mature and broadly capable. We borrowed the general organization “explicit energy assumptions → constrained schedule → inspectable output” and independently implemented the finite-grid solver and exports. No upstream runtime dependency or copied source is included. Original code/fictional examples are MIT; that does not change either upstream license. Future actual reuse would need its own retained attribution/license review.

## Concrete implementation and evidence

Watt Window implements time windows, contiguous jobs, fixed starts, peak/background capacity, entered tariffs and estimated energy. It evaluates an original schedule, searches for a lower-cost valid model allocation and exports its provenance/proof status. A budget-limited feasible result is never labeled optimal without proof; an unsuccessful bounded search is not declared infeasible. Necessary interval overloads have numerical witnesses. Sensitivity changes are explicitly hypothetical and individually solved.

`python3 scripts/verify.py` runs 17 tests and actual CLI exports for household/shop/infeasible cases plus four parameter scenarios. The tests include independent brute-force enumeration on randomized small grids, negative tariffs and exact fractions, contiguous-versus-split behavior, locked jobs, invalid baselines, sufficient versus insufficient search budgets, checkable infeasibility, and safe calendar/CSV/HTML exports. No network, appliance command, measured saving or carbon result is used in that verification.

The project is intentionally a pre-event Next Horizon prototype. It supplies testable software and truthful presentation content, with registration/shortlisting/pitch still outstanding. It is not marketed as a deployed energy management system or as work completed in the future 48-hour event.
