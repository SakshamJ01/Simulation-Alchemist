# TASK 2.3 CHECKPOINT — Build Stage 3+4+5 (CouplingTemplates + World Generation + CompositionCatalog)

**State:** COMPLETE (Stages 3+4+5 of `TASK_2.3_DESIGN.md` §22; report + docs +
regression done). This file is the compaction-safe snapshot so any future session
can finish Task 2.3 docs / resume Task 2.4 from PROJECT_STATE.md / AGENTS.md /
this file alone without trusting stale context. **Do NOT start Task 2.4 until
issued.**

Captured from a completed session; report/regression numbers below were measured
live.

---

## What the milestone adds (all present, all green)

- `src/sim_alchemist/core/world.py` — MOD: `ComponentSpec` gains optional
  `variant: str | None = None` (field order `id, config, variant`; `""`→None;
  `from_dict` reads `data.get("variant")`). Variant flows into
  `WorldDefinition.as_dict()` → `world_hash`/`run_id_of` (variant-aware identity).
- `src/sim_alchemist/core/templates.py` — NEW (Stage 3+4): `CouplingTemplate`
  (frozen; `name, bindings, world_id, contracts, schedule, operations, requires,
  executor_ref, component_configs, macro_timestep=0.2, max_steps=160, seed=0,
  config`; canonicalizes bindings via `CompositionShape`; rejects empty
  name/bindings/world_id/contracts/schedule/operations; does NOT enforce
  schedule⊆operations so synthetic SCHEDULE_INVALID templates exist; `.shape`,
  `as_dict`/`from_dict`), `CouplingTemplateRegistry` (register-only;
  `DuplicateTemplateError`; `lookup(shape)` / `by_name` / `templates()` /
  `from_sequence`), `composition_id(shape, contracts, schedule, requires,
  macro_timestep)`, `template_composition_id(template)`, `classify_composition`
  (the 6-status funnel), and `generate_world(template)` (Stage 4):
  `ComponentSpec(binding.component, template config, variant=binding.variant)`,
  adapter-free, deterministic/immutable; world `id` = `template.world_id`.
- `src/sim_alchemist/core/catalog.py` — NEW (Stage 5): `CompositionCatalog`
  pre-classifies ALL enumerated shapes at construction; `CatalogCandidate`
  (frozen: `shape, status, shape_id, bindings, missing_capabilities, template,
  reason, composition_id, generated_world`); `generated_world_available` only
  when EXECUTABLE; queries `all/executable/invalid/by_status/by_shape_id/
  status_counts/explain`; `build_composition_catalog(...)->CompositionCatalog`
  builds surfaces/templates/bindings and wires the execute closure.
- `src/sim_alchemist/core/__init__.py` — MOD: re-exports templates + catalog API.
- `chemomech/coupling.py`, `experiments/field_guided_movers/coupling.py`,
  `experiments/network_morphogenesis/coupling.py` — MOD: each now owns
  `build_*_template()` (name `morphogenesis` / `field_guided_movers` /
  `adaptive_network`; the declared schedules+contracts; `operations` = the
  coupling module's op-builder output; `executor_ref` and `component_configs`
  = its sanctioned defaults). Science stays in the coupling modules.
- `experiments/catalog.py` — NEW: `repository_surfaces()`,
  `repository_bindings()`, `build_repository_adapters(shape, template)`,
  `build_repository_catalog()`. Surfaces merged per `(component, variant)` key
  across default_registry + C + B registries (**required**: one registry id = one
  builder, so both `pymunk` variants need separate registries); adapters dispatch
  network→C registry, `walls`→default, `movers`→B registry.
- `run_catalog_demo.py` — NEW CLI: enumerates the full catalog;
  `--generate-worlds` writes the 3 EXECUTABLE worlds to YAML (default
  `generated_worlds/`).
- Tests: `tests/test_templates.py` (37), `tests/test_world_generation.py`
  (19 fast + 3 slow bitwise), `tests/test_catalog.py` (24).
- Guarded-core dict re-baselined (`tests/test_field_guided_movers.py`
  `CORE_COMMIT_HASHES`; `tests/test_network_morphogenesis.py` comment): new pins
  `__init__.py` = 7E4FF294D4C0031A0D8944A06F595EA944D991EB416998E0C89639647FE6520B,
  `world.py` = D3D7E96CCF36C260B91870611BE0AE7E0053A82CCEAFF3F316705BA1153D9236,
  `templates.py` = BB1D0CBF9BF51B37CB52BF430E942AA10B1698D87E6CB783C8670BD59045C439,
  `catalog.py` = E1BE5D90B300356B66AFCAD3B4FFBC2991C471D06D5B25D168FCAD51C39E9A0F;
  other pins unchanged.

## Classification funnel (deterministic, no simulation)

CAPABILITY_INVALID → (template lookup) → COUPLING_UNAVAILABLE → resolve_contracts
→ COUPLING_INVALID → schedule ops ⊆ registered ops → SCHEDULE_INVALID → native
dt divides macro_timestep → CLOCK_INVALID → EXECUTABLE. Template found for a
non-executable shape still yields `composition_id`; EXECUTABLE has empty reasons.

## Key numbers (measured)

- Catalog = **23 shapes** (5/9/7/2 per size) → statuses **16 CAPABILITY_INVALID /
  4 COUPLING_UNAVAILABLE / 3 EXECUTABLE** (0 COUPLING_INVALID, 0 other).
- EXECUTABLE: A `{mesa, py-pde, pymunk/walls}`→morphogenesis, B `{py-pde,
  pymunk/movers}`→field_guided_movers, C `{py-pde, pymunk/walls, network}`→
  adaptive_network. COUPLING_UNAVAILABLE: `{py-pde, pymunk/movers, mesa}`,
  `{py-pde, pymunk/walls, mesa, network}`, `{py-pde, pymunk/movers, network}`,
  `{mesa, network, py-pde, pymunk/movers}`.
- Full pytest suite (incl. 6 slow): **359 passed / 0 failed** (fast `-m "not slow"`
  = 353 passed, 6 deselected). Slow bitwise: generated-world worlds reproduce the
  facade trajectories byte-identically (A/B/C via plain composer + default/C/B
  registry, noop schedule run).
- `run_catalog_demo.py --generate-worlds` → 23 shapes, 16/4/3, writes 3 YAML
  worlds (`generated_worlds/` if no `--worlds-dir`).

## Environment / commands (unchanged)

`uv run pytest`, `uv run pytest tests/ -m "not slow"`, `uv run ruff check .`,
`uv run pyright`, `uv run python run_validation.py`, `uv run python
run_stability.py`, `uv run python run_catalog_demo.py`. Windows PowerShell.

## Not implemented (Task 2.4 & beyond — do NOT build until issued)

`CompositionSearcher`, search integration, `composition_id` lineage table write/
lineage UX, discovery demo, cross-composition discovery, automatic coupling
inference, plugin discovery, AI/ML/optimizer/distributed execution.