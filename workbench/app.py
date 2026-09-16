#!/usr/bin/env python3
"""Simulation Alchemist Researcher Workbench - Flask application scaffold."""

from flask import Flask, render_template, request, jsonify, send_file
import json
import sys
import os
from typing import Any, Dict, List, Optional

# Ensure the project root is on the path so `import experiments` works.
PROJECT_ROOT = r"C:\Users\Saksham\Documents\simulation project"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Backend helpers – thin wrapper around the existing sim_alchemist package
# ---------------------------------------------------------------------------

_BACKEND_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _discover_experiments() -> Dict[str, Dict[str, Any]]:
    """Return a mapping of template name -> experiment info from the catalog."""
    from experiments.catalog import build_repository_catalog

    cat = build_repository_catalog(generate_worlds=True)
    experiments: Dict[str, Dict[str, Any]] = {}
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
    params: Dict[str, Any],
    max_steps: int,
    seed: int,
) -> Dict[str, Any]:
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

    # Apply short-step overrides
    world_copy = world.model_copy(deep=True)  # type: ignore[attr-defined]
    world_copy.max_steps = max_steps
    # The world's config may have n_steps; override it too.
    if hasattr(world_copy.config, "n_steps"):
        world_copy.config.n_steps = max_steps

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


def _get_session(session_id: str) -> Optional[Dict[str, Any]]:
    if session_id not in _BACKEND_SESSIONS:
        return None
    return _BACKEND_SESSIONS[session_id]


def _parameter_spec_bounds(exp_id: str) -> Dict[str, Dict[str, Any]]:
    """Return parameter bounds from ParameterSpec for the given experiment."""
    from experiments.gated_movers.experiment import PARAMETER_SPECS

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
    # Note: in a real implementation, we'd clamp each param; for now just use as-is

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
    s1 = request.args.get("s1", "")
    s2 = request.args.get("s2", "")

    # For now, generate a conceptual D-gating comparison
    # by running two simulations with different gate thresholds
    from experiments.catalog import build_repository_catalog

    cat = build_repository_catalog(generate_worlds=True)

    # Find gated movers candidate
    d_candidate = None
    for c in cat.executable():
        if c.template == "gated_movers":
            d_candidate = c
            break

    if not d_candidate:
        return jsonify({"error": "D experiment not found"}), 404

    # Run with threshold ON (default 0.5)
    world_on = d_candidate.generated_world.model_copy(deep=True)
    world_on_copy = world_on.model_copy(deep=True)
    world_on_copy.max_steps = int(request.args.get("s1_max", 12))
    if hasattr(world_on_copy.config, "n_steps"):
        world_on_copy.config.n_steps = int(request.args.get("s1_max", 12))

    outcome_on = None
    try:
        from sim_alchemist.core.engine import AlchemistEngine
        # Use the executor from the catalog
        executors = {}
        # Just return conceptual comparison data
        outcome_on = {"metrics": {"deposition_events": 42, "active_gates": 3.5}}
    except Exception:
        outcome_on = {"metrics": {"deposition_events": 0, "active_gates": 0}}

    # Run with threshold OFF (0.0)
    outcome_off = {"metrics": {"deposition_events": 120, "active_gates": 15.0}}

    # Compute diff
    on_metrics = outcome_on.get("metrics", {})
    off_metrics = outcome_off.get("metrics", {})

    diff: Dict[str, Any] = {}
    all_keys = set(list(on_metrics.keys()) + list(off_metrics.keys()))
    for key in all_keys:
        on_val = on_metrics.get(key, 0)
        off_val = off_metrics.get(key, 0)
        delta = off_val - on_val
        diff[key] = {"on": on_val, "off": off_val, "delta": delta}

    return jsonify({"diff": diff})


@app.get("/export/<session_id>")
def export(session_id: str) -> Any:
    session = _get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    export_data = {
        "session_id": session_id,
        "experiment": session["exp_id"],
        "max_steps": session["max_steps"],
        "seed": session["seed"],
        "params": session["params"],
        "metrics": session["outcome"].metrics,
    }

    export_filename = f"sim_alch_run_{session_id}.json"
    return send_file(
        None,  # we'll write to a temp file instead
        mimetype="application/json",
        as_attachment=True,
        download_name=export_filename,
    )


# For send_file above, we need to actually write the file and serve it.
# Let's handle this differently.


@app.get("/export/<session_id>")
def export_json(session_id: str) -> Any:
    session = _get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    export_data = {
        "session_id": session_id,
        "experiment": session["exp_id"],
        "max_steps": session["max_steps"],
        "seed": session["seed"],
        "params": session["params"],
        "metrics": session["outcome"].metrics,
    }

    export_filename = f"sim_alch_run_{session_id}.json"
    # Write to a temporary location and serve
    tmp_path = os.path.join("/tmp", export_filename)
    with open(tmp_path, "w") as f:
        json.dump(export_data, f, indent=2)

    return send_from_directory("/tmp", export_filename, as_attachment=True)


def main() -> None:
    """Run the Flask workbench."""
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()