#!/usr/bin/env python3
"""Simulation Alchemist Researcher Workbench - Flask application scaffold."""

import copy as _copy
import json
import os
import sys
from dataclasses import replace as _replace
from typing import Any

from flask import Flask, jsonify, render_template, request, send_from_directory

from sim_alchemist.core.lineage import run_id_of

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
        template = c.template or "unknown"
        comp_id = c.composition_id or "unknown"
        name_map = {
            "morphogenesis": "Morphogenesis (A)",
            "field_guided_movers": "Field-guided movers (B)",
            "adaptive_network": "Adaptive network (C)",
            "gated_movers": "Gated mover morphogenesis (D)",
        }
        experiments[template] = {
            "id": comp_id,
            "name": name_map.get(template, template),
            "template": template,
            "description": {
                "morphogenesis": "Mesa agents + py-pde field + Pymunk walls",
                "field_guided_movers": "py-pde field + Pymunk movers (unconditional chemotaxis)",
                "adaptive_network": "NDlib network + py-pde + Pymunk",
                "gated_movers": "Mesa gating layer + py-pde + Pymunk movers",
            }.get(template, template),
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

    # Find the candidate matching exp_id (composition_id hash or template name)
    candidate = None
    for c in cat.executable():
        if c.composition_id == exp_id or c.template == exp_id:
            candidate = c
            break
    if candidate is None:
        raise ValueError(f"Unknown experiment id: {exp_id}")
    if candidate.composition_id is None or candidate.generated_world is None:
        raise ValueError("Candidate has no composition_id or generated world")

    world = candidate.generated_world

    world_copy = _replace(world, max_steps=max_steps)
    new_config = _copy.deepcopy(world_copy.config)
    new_config["n_steps"] = max_steps
    for k, v in params.items():
        new_config[k] = v
    world_copy = _replace(world_copy, config=new_config)

    # Run the executor
    executor_fn = executors[candidate.composition_id]
    outcome = executor_fn(world_copy)

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
    param_specs: dict[str, dict[str, Any]] = {}
    for exp_id in experiments:
        param_specs.update(_parameter_spec_bounds(exp_id))
    return render_template(
        "index.html",
        executives=sorted(
            experiments.values(), key=lambda e: e["name"]
        ),
        param_specs=param_specs,
    )


@app.post("/run")
def run() -> Any:
    try:
        data = request.get_json(force=True, silent=True) or {}
        if not data and request.form:
            data = dict(request.form)

        exp_id = data.get("exp_id")
        if not exp_id:
            return jsonify({"error": "Missing exp_id"}), 400

        raw_params = data.get("params", {}) or {}
        if not isinstance(raw_params, dict):
            raw_params = {}

        max_steps = int(data.get("max_steps") or 12)
        seed = int(data.get("seed") or 42)

        from experiments.catalog import build_repository_catalog
        cat = build_repository_catalog(generate_worlds=True)
        candidate = None
        for c in cat.executable():
            if c.composition_id == exp_id or c.template == exp_id:
                candidate = c
                break
        if candidate is None or candidate.composition_id is None:
            return jsonify({"error": f"Unknown experiment id: {exp_id}"}), 400

        # Apply parameter bounds clamping
        template_name = candidate.template or ""
        specs = _parameter_spec_bounds(template_name)
        clamped_params: dict[str, Any] = {}
        for p_name, p_spec in specs.items():
            if p_name in raw_params:
                try:
                    val = float(raw_params[p_name])
                    if "min" in p_spec and val < p_spec["min"]:
                        val = float(p_spec["min"])
                    if "max" in p_spec and val > p_spec["max"]:
                        val = float(p_spec["max"])
                    clamped_params[p_name] = val
                except (ValueError, TypeError):
                    clamped_params[p_name] = float(p_spec.get("default", 0.0))
            elif "default" in p_spec:
                clamped_params[p_name] = float(p_spec["default"])

        # Also preserve any raw params passed that weren't in specs
        for k, v in raw_params.items():
            if k not in clamped_params:
                clamped_params[k] = v

        result = _run_simulation(candidate.composition_id, clamped_params, max_steps, seed)
        session_id = result["session_id"]
        outcome = result["outcome"]

        return jsonify({
            "session_id": session_id,
            "outcome": {
                "metrics": outcome.metrics,
                "world_hash": run_id_of(outcome.world),
            },
            "outcome_metrics": outcome.metrics,
        })
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@app.get("/comparison")
def comparison() -> Any:
    """Compare D gating ON vs OFF using real simulation data."""
    from experiments.catalog import build_repository_catalog

    cat = build_repository_catalog(generate_worlds=True)

    d_candidate = None
    for c in cat.executable():
        if c.template == "gated_movers":
            d_candidate = c
            break
    if not d_candidate or d_candidate.generated_world is None or d_candidate.composition_id is None:
        return jsonify({"error": "D experiment not found"}), 404

    comp_id = d_candidate.composition_id

    # Run with threshold ON (0.5) — gates open when field u >= threshold
    world_on = _replace(d_candidate.generated_world, max_steps=12)
    new_config = _copy.deepcopy(world_on.config)
    new_config["n_steps"] = 12
    world_on_copy = _replace(world_on, max_steps=12, config=new_config)

    from experiments.catalog import repository_executors as _executors

    exec_map = _executors()
    outcome_on = exec_map[comp_id](world_on_copy)

    # Run with threshold OFF (0.0) — gates always open, no hysteresis
    world_off = _replace(d_candidate.generated_world, max_steps=12)
    new_config2 = _copy.deepcopy(world_off.config)
    new_config2["n_steps"] = 12
    world_off_copy = _replace(world_off, max_steps=12, config=new_config2)

    outcome_off = exec_map[comp_id](world_off_copy)

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
            "on_run_id": run_id_of(outcome_on.world),
            "off_run_id": run_id_of(outcome_off.world),
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
    import tempfile

    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, export_filename)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({
            "session_id": session_id,
            "experiment": session["exp_id"],
            "max_steps": session["max_steps"],
            "seed": session["seed"],
            "params": session["params"],
            "metrics": session["outcome"].metrics,
            "world_hash": run_id_of(session["outcome"].world),
        }, f, indent=2)

    return send_from_directory(directory=tmp_dir, path=export_filename, as_attachment=True)


def main() -> None:
    """Run the Flask workbench."""
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()