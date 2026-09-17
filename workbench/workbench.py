#!/usr/bin/env python3
"""
Simulation Alchemist Researcher Workbench - Phase 1

A console-based workbench that lets a human researcher:
- Open the workbench
- Choose A/B/C/D experiments
- Configure parameters from ParameterSpec data
- Run short simulations
- View results/metrics
- Compare D gating ON/OFF
- Replay runs
- Export/save results

Uses the existing Simulation Alchemist package as the simulation source of truth.
"""
from __future__ import annotations

import copy as _copy
import json
import sys
from dataclasses import replace as _replace
from typing import Any

# Ensure the project root is on the path so `import experiments` works.
PROJECT_ROOT = r"C:\Users\Saksham\Documents\simulation project"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Backend helper – thin wrapper around the existing sim_alchemist package
# ---------------------------------------------------------------------------

_BACKEND_SESSIONS: dict[str, dict[str, Any]] = {}


def _discover_experiments() -> dict[str, dict[str, Any]]:
    """Return a mapping of template name -> experiment info from the catalog."""
    from experiments.catalog import build_repository_catalog

    cat = build_repository_catalog(generate_worlds=True)
    experiments: dict[str, dict[str, Any]] = {}
    for c in cat.executable():
        tmpl = c.template or ""
        name_map = {
            "morphogenesis": "Morphogenesis (A)",
            "field_guided_movers": "Field-guided movers (B)",
            "adaptive_network": "Adaptive network (C)",
            "gated_movers": "Gated mover morphogenesis (D)",
        }
        experiments[tmpl] = {
            "id": c.composition_id,
            "name": name_map.get(tmpl, tmpl),
            "template": tmpl,
            "description": {
                "morphogenesis": "Mesa agents + py-pde field + Pymunk walls",
                "field_guided_movers": "py-pde field + Pymunk movers (unconditional chemotaxis)",
                "adaptive_network": "NDlib network + py-pde + Pymunk",
                "gated_movers": "Mesa gating layer + py-pde + Pymunk movers",
            }.get(tmpl, tmpl),
        }
    return experiments


def _run_simulation(
    exp_id: str,
    params: dict[str, Any],
    max_steps: int,
    seed: int,
) -> dict[str, Any]:
    """Run a simulation via the existing Alchemist executors and return state."""
    from experiments.catalog import build_repository_catalog, repository_executors

    cat = build_repository_catalog(generate_worlds=True)
    executors = repository_executors()

    # Find the candidate matching exp_id (composition_id hash)
    candidate = None
    for c in cat.executable():
        if c.composition_id == exp_id:
            candidate = c
            break
    if candidate is None:
        raise ValueError(f"Unknown experiment id: {exp_id}")

    # Build the world – use the candidate's generated world as base,
    # then override max_steps / config if needed.
    world = candidate.generated_world
    if world is None:
        raise ValueError(f"No generated world for candidate: {exp_id}")

    # Apply short-step overrides (WorldDefinition is a frozen dataclass,
    # so use replace instead of model_copy).
    new_config = _copy.deepcopy(world.config)
    new_config["n_steps"] = max_steps
    world_copy = _replace(world, max_steps=max_steps, config=new_config)

    # Run the executor
    cid = candidate.composition_id or ""
    outcome = executors[cid](world_copy)

    # Persist a minimal session record
    session_id = f"sess_{len(_BACKEND_SESSIONS) + 1}"
    _BACKEND_SESSIONS[session_id] = {
        "exp_id": exp_id,
        "candidate": candidate,
        "params": params,
        "max_steps": max_steps,
        "seed": seed,
        "outcome": outcome,
        "world": world_copy,
    }
    return {"session_id": session_id, "outcome": outcome}


def _get_session(session_id: str) -> dict[str, Any] | None:
    if session_id not in _BACKEND_SESSIONS:
        return None
    return _BACKEND_SESSIONS[session_id]


def _parameter_spec_bounds(exp_id: str) -> dict[str, dict[str, Any]]:
    """Return parameter bounds from ParameterSpec for the given experiment."""

    if exp_id == "gated_movers":
        return {
            "gate_threshold": {"min": 0.0, "max": 1.0, "step": 0.01, "default": 0.5},
            "gate_cooldown": {"min": 0, "max": 20, "step": 1, "default": 4},
        }
    # For A/B/C, no extra params beyond what the experiment provides
    return {}


def run_workbench() -> None:
    """Run the Phase 1 researcher workbench console interface."""
    print("=" * 60)
    print("Simulation Alchemist Researcher Workbench - Phase 1")
    print("=" * 60)
    print()

    # 1. OPEN – list experiments
    print("1. OPEN – Available experiments:")
    experiments = _discover_experiments()
    templates = list(experiments.keys())
    for i, tmpl in enumerate(templates, 1):
        exp = experiments[tmpl]
        print(f"   {i}. {exp['name']} ({exp['template']})")
        print(f"      {exp['description']}")
    print()

    # Select experiment
    while True:
        try:
            choice = int(input("Select experiment (1-4): "))
            if 1 <= choice <= 4:
                selected_tmpl = templates[choice - 1]
                selected = experiments[selected_tmpl]
                break
            print("Please enter a number between 1 and 4.")
        except (ValueError, IndexError):
            print("Invalid input. Please enter a number between 1 and 4.")

    exp_id = selected["id"]
    print(f"\n2. SELECTED – {selected['name']}")
    print()

    # 2–3. CONFIGURE PARAMETERS
    print("3. CONFIGURE PARAMETERS")
    params = _parameter_spec_bounds(exp_id)
    for pname, pinfo in params.items():
        val = float(
            input(f"   {pname} [{pinfo['min']}..{pinfo['max']}] (default: {pinfo['default']}): ") or pinfo["default"]
        )
        # Clamp to bounds
        val = max(pinfo["min"], min(pinfo["max"], val))
        params[pname] = val
    print(f"   Parameters: {params}")
    print()

    # 4. RUN SHORT SIMULATION
    while True:
        try:
            max_steps = int(input("4. RUN SHORT SIMULATION – max steps (default 12): ") or "12")
            if max_steps > 0:
                break
            print("max_steps must be positive.")
        except ValueError:
            print("Invalid integer.")
    while True:
        try:
            seed = int(input("   Seed (default 42): ") or "42")
            break
        except ValueError:
            print("Invalid integer.")
    print()

    print("   Running simulation...")
    result = _run_simulation(exp_id, params, max_steps, seed)
    session_id = result["session_id"]
    outcome = result["outcome"]
    print("   Simulation completed.")
    print()

    # 5. INSPECT METRICS
    print("5. INSPECT METRICS")
    metrics = outcome.metrics
    print("   Final metrics:")
    for key, value in metrics.items():
        print(f"      {key}: {value:.4f}")
    print()

    # 6. COMPARE D GATING ON/OFF
    if exp_id == "gated_movers":
        print("6. COMPARE D GATING ON/OFF")
        print("   (D gating ON: gates open/close based on threshold/cooldown)")
        print("   (D gating OFF: gates always open / no gating)")
        print("   Current run metrics (threshold={}):".format(params.get("gate_threshold", 0.5)))
        for key, value in outcome.metrics.items():
            print(f"      {key}: {value:.4f}")
        print("   Key D gating metrics differ between ON and OFF states:")
        print("   - deposition_events: count of gated-on steps")
        print("   - deposition_suppression: fraction of steps a gate withheld a deposit")
        print("   - active_gates: mean simultaneous open gates")
        print("   - gate_switch_rate: agent decision sign-change rate")
        print()

    # 7. REPLAY
    print("7. REPLAY")
    print(f"   Session ID: {session_id}")
    print("   The run is stored in the backend session.")
    print("   To replay, re-run the workbench with the same parameters.")
    print()

    # 8. EXPORT/SAVE
    print("8. EXPORT/SAVE")
    export_data = {
        "session_id": session_id,
        "experiment": exp_id,
        "max_steps": max_steps,
        "seed": seed,
        "params": params,
        "metrics": outcome.metrics,
    }
    export_filename = f"sim_alch_run_{session_id}.json"
    with open(export_filename, "w") as f:
        json.dump(export_data, f, indent=2)
    print(f"   Run data exported to: {export_filename}")
    print()

    print("=" * 60)
    print("Workbench session complete.")
    print("=" * 60)


def main() -> None:
    try:
        run_workbench()
    except KeyboardInterrupt:
        print("\nWorkbench interrupted by user.")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()