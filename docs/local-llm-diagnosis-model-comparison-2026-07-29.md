# Local LLM comparison for AI Diagnosis — 2026-07-29

## What this is

The dashboard's "AI Diagnosis" section (`dashboard/app.py`) calls
`tools.agentic_loop.diagnose()` with `offer_tools=False` — the model gets the
current run's telemetry, a drift report, and the real text of
`src/nav_fleet/config/nav2_params.yaml`, and writes a free-text analysis plus
prose-described recommendations (parsed best-effort by
`extract_prose_recommendations()`/`describe_potential_changes()`).

After the original tool-calling bug was fixed (see `tools/CLAUDE.md`), the
next open question was whether a bigger or different local model would
produce meaningfully better diagnoses. This is the record of that
investigation: 8 models, same live dashboard pipeline, same real run under
test (`id=530`, `mission2`, `FAIL`), timed and fact-checked against the real
config file.

## Method

Each model was run through the exact `offer_tools=False` pipeline the
dashboard uses (either by clicking the live "Diagnose with AI"/"Experimental
AI" buttons, or an identical standalone harness calling `diagnose()`
directly for models not yet wired to a button). Every parameter claim in this
table was checked against the real `nav2_params.yaml`, not taken at face
value — that verification is what "grounding" below refers to.

## Results

| Model | Time | Quality Summary |
|---|---|---|
| Llama 3.1 8B | 5.4s | Format didn't parse (CLI-flag style: `--param X --value Y`). Fastest overall, weakest grounding — invented a costmap path (`local_costmap/obstacle_layer/resolution`) that doesn't exist, and misattributed `rotate_to_heading_angular_vel` to `planner_server` when it's really under `controller_server`. |
| Qwen 2.5 14B-instruct (project default going in) | 11.2s | Format didn't parse (malformed JSON, tool name as a dict key instead of a value). Contained a literal Chinese-language fragment leaked into a field value — a real quality issue independent of formatting. |
| Gemma 3 12B | 16.5s | Format parsed cleanly and completely — the best extraction result of the whole comparison (used the original kwargs-style syntax the parser was built around). But proposed setting `odom_frame_id` to `"base_link"` — a real TF-tree conceptual error (confuses the odometry frame with the robot's base frame, which isn't even named `base_link` on this robot — it's `base_footprint`) that could actively break localization if applied. |
| Phi-4 14B | 28.7s | Format parsed but ugly (a nested JSON object under the key `"parameter"` — singular — collided with an existing alias and got dumped as a raw dict string into the Summary). Best reasoning of the comparison: correctly explained *why* `rotate_to_heading_angular_vel` is 0.5 (matches the real, documented Session 16 rationale) — but then recommended raising it to 1.0 anyway, contradicting its own explanation. Correctly verified `local_costmap` width/height (4×4m) and that `collision_monitor` is effectively a no-op. |
| Gemma 2 27B | 45.4s | Format didn't parse (YAML-fenced recommendation, no parens/braces at all). Best prose coherence of the comparison. Correctly recalled both real inflation radii (`local_costmap` 0.25, `global_costmap` 0.30) completely unprompted. Only model that left `rotate_to_heading_angular_vel` alone entirely — no regression proposal. Only produced one actionable recommendation, and it was the one the parser missed. |
| Qwen 2.5 32B | 61.7s | Format mostly didn't parse (comma-separated quoted positional args). Proposed increasing `rotate_to_heading_angular_vel` 0.5→0.6 — the first instance of what became a recurring pattern: reversing part of a documented, deliberate tuning decision (Session 16 Task 9e slowed this specifically to give AMCL more lidar scans per radian). |
| Gemma 3 27B | 91.5s | Format nearly parsed — genuinely clean JSON, but used the key `"tool_call"` where the parser expects `"tool"`, so extraction still missed all 5 items. Correctly recalled `global_costmap.plugins`' real 3-item list before proposing a 4th, fabricated `"recovery_layer"` — not a real Nav2 costmap plugin type (recovery behaviors are a separate subsystem, `behavior_server`, not a costmap layer). ~2x slower than Gemma 2 27B at the identical parameter size — the one same-size, cross-generation data point in this comparison. |
| Llama 3.3 70B | 232.4s | Format didn't parse (plain prose-colon bullets, e.g. `propose_nav_param_change: Change the X parameter...`). Best grounding of the entire comparison — correctly recalled both inflation radii *and* `collision_monitor.min_points=6` (all verified exact). Only model to propose *decreasing* `rotate_to_heading_angular_vel` further (0.5→0.2), which is internally consistent with the original documented rationale — though it cuts against the project's separately-stated goal of a faster demo. By far the slowest response of the night (~3.9 min). |

## What this showed, independent of any one model

1. **Format inconsistency is architectural, not a model-capability problem.**
   Every one of the 8 runs used a different output shape — kwargs-style,
   colon-positional, flat JSON, JSON with a nested `"parameter"` object,
   comma-quoted positional, YAML-fenced, plain prose-colon, CLI-flag style,
   and JSON using `"tool_call"`/`"parameters"` instead of `"tool"`/`"input"`.
   Bigger models did not converge on a shared format — if anything, the two
   closest near-misses to parsing (Gemma 3 12B's clean success, Gemma 3
   27B's one-key-name miss) came from the same family at two different
   sizes, with opposite outcomes. **5 of 8 runs produced a Summary that
   flatly contradicted the raw text directly above it** ("No specific
   changes were identified" while real recommendations were plainly
   visible) — this is the clearest, most repeated finding of the whole
   investigation.
2. **Grounding accuracy trended with model capability, but imperfectly.**
   The two largest/most capable models (Gemma 2 27B, Llama 3.3 70B)
   consistently recalled real config values (inflation radii,
   `min_points`) without being fed them — smaller models never did this
   reliably. But even the best-grounded models made real domain-level
   mistakes when *proposing* something new (Gemma 3 12B's `odom_frame_id`
   confusion, Gemma 3 27B's fabricated `recovery_layer` plugin) — grounding
   in the injected file and correctness of a *new* proposal are different
   skills, and neither model size fully solved the second one.
3. **Speed and grounding moved in opposite directions across the whole
   comparison** — fastest (Llama 3.1 8B, 5.4s) was weakest on facts;
   slowest (Llama 3.3 70B, 232.4s) was strongest.
4. **Same-size, cross-generation comparison (Gemma 2 27B vs. Gemma 3 27B):**
   newer generation was ~2x slower on this hardware and produced more
   candidate recommendations with generally good grounding on *existing*
   values, but introduced its own new fabrication when proposing something
   the file doesn't already contain. Not a clean "newer is strictly
   better" result.

## Decision

**`PRIMARY_MODEL` ("Diagnose with AI") → Phi-4 14B.** Fast enough to click
routinely (28.7s), no fabrication/hallucination issues found (unlike Qwen
14B's language leak or Llama 3.1 8B's invented parameter path), and the best
reasoning transparency of any model in its speed class — its one real flaw
(recommending a change it had just argued against) is exactly the kind of
thing the project's human-approval design exists to catch.

**`EXPERIMENTAL_MODEL` ("Experimental AI — May take a long time") → Llama
3.3 70B.** Best grounding of the whole comparison, and the ~4-minute latency
is acceptable for a button explicitly labeled as a slow deep-dive. Known gap
at the time this was written: its output format wasn't reliably parsed by
`extract_prose_recommendations()`, so its Summary section would likely have
undersold its actual content — see the update below.

## Update — 2026-07-29, later same session: JSON-envelope redesign built

The format-inconsistency finding above (5 of 8 runs) was the direct trigger
for a same-day fix: the `offer_tools=False` path (both dashboard buttons) now
asks for one grammar-constrained JSON envelope (`{"analysis": ...,
"recommendations": [...]}`, enforced via Ollama's `format='json'`) instead of
free-text prose with recommendations embedded in it. Full details in
`tools/CLAUDE.md`'s `agentic_loop.py` entry. Live-verified against `phi4`
immediately after building it: clean prose analysis, all 4 recommendations
parsed correctly in the Summary — the first fully clean parse of this whole
investigation, on the first live click. This doesn't change any of the
model-comparison findings above (those were all real, captured before the
fix) — it addresses finding #1 (format inconsistency) going forward; findings
#2-4 (grounding accuracy, speed/grounding tradeoff, generation comparison)
are about model behavior, not the parsing layer, and still stand.

## Not pursued further

- Llama 3.4 in the 70B class doesn't exist — Meta went straight from 3.3 to
  Llama 4 (Scout 109B MoE, Maverick 400B, Behemoth 2T preview-only), which
  don't map onto a "next 70B" at all.
- Gemma 2/Gemma 3 have no size between single digits and 27B (no `15b`).
- Llama 3.x has no size between 8B and 70B (no `14b`).
