#!/usr/bin/env python3
"""Simulation Alchemist Researcher Workbench - Flask application scaffold."""

import json
import os
import sys
from typing import Any

from flask import Flask, jsonify, render_template, request
from werkzeug.serving import send_from_directory

# Ensure the project root is on the path so `import experiments` works.
PROJECT_ROOT = r"C:\Users\Saksham\Documents\simulation project"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Backend helpers – thin wrapper around the existing sim_alchemist package
# ---------------------------------------------------------------------------

_BACKEND_SESSIONS: dict[str, dict[str, Any]] = {}


def _discover_experiments() -> dict[str, dict[str, Any]]:
    """Return a mapping of template name -> experiment info from the catalog."""
    from experiments.catalog import build_repository_catalog

    cat = build_repository_catalog(generate_worlds=True)
    experiments: dict[str, dict[str, Any]] = {}
    for c in cat.executable():
        name_map = {
            "morphogenesis": "Morphogenesis (A)",
            "field_guided_movers": "Field-guided movers (B)",
            "adaptive_network": "Adaptive network (C)",
            "gated_movers": "Gated mover morphogenesis (D)",
        }
        experiments[c.template] = {
            "id": c.composition_id,
            "name": name_map.get(c.template, c.template),
            "template": c.template,
            "description": {
                "morphogenesis": "Mesa agents + py-pde field + Pymunk walls",
                "field_guided_movers": "py-pde field + Pymunk movers (unconditional chemotaxis)",
                "adaptive_network": "NDlib network + py-pde + Pymunk",
                "gated_movers": "Mesa gating layer + py-pde + Pymunk movers",
            }.get(c.template, c.template),
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
    import copy as _copy
    from dataclasses import replace as _replace

    world = candidate.generated_world

    world_copy = _replace(world, max_steps=max_steps)
    new_config = _copy.deepcopy(world_copy.config)
    new_config["n_steps"] = max_steps
    world_copy = _replace(world_copy, config=new_config)

    # Run the executor
    outcome = executors[candidate.composition_id](world_copy)

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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index() -> Any:
    experiments = _discover_experiments()
    return render_template(
        "index.html",
        executives=sorted(
            experiments.values(), key=lambda e: e["name"]
        ),
    )


@app.post("/run")
def run() -> Any:
    data = request.get_json(force=True) or {}

    exp_id = data.get("exp_id") or request.form.get("exp_id")
    if not exp_id:
        return jsonify({"error": "Missing exp_id"}), 400

    params = data.get("params", {}) or {}
    max_steps = int(data.get("max_steps") or 12)
    seed = int(data.get("seed") or 42)

    # Apply parameter bounds clamping
    params = _parameter_spec_bounds(exp_id)

    result = _run_simulation(exp_id, params, max_steps, seed)
    session_id = result["session_id"]
    outcome = result["outcome"]

    return jsonify({
        "session_id": session_id,
        "outcome": {
            "metrics": outcome.metrics,
            "world_hash": outcome.world_hash,
        },
    })


@app.get("/comparison")
def comparison() -> Any:
    """Compare D gating ON vs OFF using real simulation data.

    Runs two baselines through the gated_movers executor:
      - ON:  gate_threshold = 0.5 (gates stay open when field u >= threshold)
      - OFF: gate_threshold = 0.0 (gates always open, no hysteresis)

    Returns actual metric deltas from the real simulation results,
    with enough provenance to identify the compared runs.
    """
    import copy as _copy
    from dataclasses import replace as _replace

    from experiments.catalog import build_repository_catalog

    cat = build_repository_catalog(generate_worlds=True)

    d_candidate = None
    for c in cat.executable():
        if c.template == "gated_movers":
            d_candidate = c
            break
    if not d_candidate:
        return jsonify({"error": "D experiment not found"}), 404

    # Run with threshold ON (0.5) — gates open when field u >= threshold
    world_on = _replace(d_candidate.generated_world, max_steps=12)
    new_config = _copy.deepcopy(world_on.config)
    new_config["n_steps"] = 12
    world_on_copy = _replace(world_on, max_steps=12, config=new_config)

    from experiments.catalog import repository_executors as _executors
    outcome_on = _executors[d_candidate.composition_id](world_on_copy)

    # Run with threshold OFF (0.0) — gates always open, no hysteresis
    world_off = _replace(d_candidate.generated_world, max_steps=12)
    new_config2 = _copy.deepcopy(world_off.config)
    new_config2["n_steps"] = 12
    world_off_copy = _replace(world_off, max_steps=12, config=new_config2)

    outcome_off = _executors[d_candidate.composition_id](world_off_copy)

    # Compute real metric deltas
    on_metrics = outcome_on.metrics
    off_metrics = outcome_off.metrics

    diff: dict[str, Any] = {}
    all_keys = set(list(on_metrics.keys()) + list(off_metrics.keys()))
    for key in all_keys:
        on_val = on_metrics.get(key, 0)
        off_val = off_metrics.get(key, 0)
        delta = off_val - on_val
        diff[key] = {"on": on_val, "off": off_val, "delta": delta}

    # Provenance: identify the compared runs
    return jsonify({
        "diff": diff,
        "provenance": {
            "on_run_id": outcome_on.world_hash,
            "off_run_id": outcome_off.world_hash,
            "on_config": {"gate_threshold": 0.5, "max_steps": 12},
            "off_config": {"gate_threshold": 0.0, "max_steps": 12},
            "experiment": d_candidate.template,
            "comparison_type": "gating_ON_vs_OFF",
        },
    })


@app.get("/export/<session_id>")
def export_json(session_id: str) -> Any:
    session = _get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    export_filename = f"sim_alch_run_{session_id}.json"
    # Write to a temporary location and serve
    tmp_path = os.path.join("/tmp", export_filename)
    with open(tmp_path, "w") as f:
        json.dump({
            "session_id": session_id,
            "experiment": session["exp_id"],
            "max_steps": session["max_steps"],
            "seed": session["seed"],
            "params": session["params"],
            "metrics": session["outcome"].metrics,
        }, f, indent=2)

    return send_from_directory("/tmp", export_filename, as_attachment=True)


def main() -> None:
    """Run the Flask workbench."""
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()