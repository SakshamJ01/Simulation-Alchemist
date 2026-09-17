#!/usr/bin/env python3
"""Simulation Alchemist Researcher Workbench - Phase 2 Trusted Experiment Lab."""

from __future__ import annotations

import copy as _copy
import io
import sys
import time
import uuid
from dataclasses import replace as _replace
from pathlib import Path
from typing import Any

import numpy as np
from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_file,
)

# Ensure the project root is on sys.path before importing application modules
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sim_alchemist.core.lineage import run_id_of
from workbench.discovery import (
    estimate_discovery_runtime,
    get_default_mutation_space,
    get_experiment_parameter_specs,
    run_discovery_pass,
)
from workbench.export_import import (
    export_reproducible_record,
    export_result_json,
    export_trajectory_archive,
    import_reproducible_record,
)
from workbench.store import ExperimentRecord, WorkbenchStore

app = Flask(__name__)
store = WorkbenchStore()

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


def _serialize_trajectory(trajectory: Any) -> dict[str, Any]:
    """Extract and serialize real trajectory frames for frontend visualization."""
    if trajectory is None:
        return {"available": False, "total_steps": 0, "field_frames": [], "movers": {}, "walls": {}}

    u_snaps = getattr(trajectory, "u_snaps", [])
    total_steps = len(u_snaps) if u_snaps else 0

    field_frames: list[dict[str, Any]] = []
    # If total_steps > 50, sample up to 30 snapshots uniformly; otherwise keep all
    step_indices = list(range(total_steps))
    if total_steps > 50:
        step_stride = max(1, total_steps // 30)
        sampled_indices = set(range(0, total_steps, step_stride))
        sampled_indices.add(total_steps - 1)
        step_indices = sorted(sampled_indices)

    for idx in step_indices:
        arr = u_snaps[idx]
        if hasattr(arr, "tolist"):
            min_val = float(np.min(arr))
            max_val = float(np.max(arr))
            field_frames.append({
                "step": idx,
                "shape": list(arr.shape),
                "min": min_val,
                "max": max_val,
                "grid": [[round(float(v), 3) for v in row] for row in arr],
            })

    # Extract mover positions across steps (B & D)
    positions_dict = getattr(trajectory, "positions", {})
    movers_data: dict[str, list[list[float]]] = {}
    for m_id, pts in positions_dict.items():
        movers_data[str(m_id)] = [[round(float(x), 4), round(float(y), 4)] for (x, y) in pts]

    # For Experiment A (walls)
    wall_tracks = getattr(trajectory, "wall_tracks", {})
    walls_data: dict[str, list[list[float]]] = {}
    for w_id, pts in wall_tracks.items():
        walls_data[str(w_id)] = [[round(float(coord), 4) for coord in pt] for pt in pts]

    # Gating specifics (D)
    active_gates = getattr(trajectory, "active_gates", [])
    suppressed_gates = getattr(trajectory, "suppressed_gates", [])
    gate_deposits = getattr(trajectory, "gate_deposits", [])
    gate_switches = getattr(trajectory, "gate_switches", [])

    # Dynamic metrics per step
    speeds = [round(float(s), 5) for s in getattr(trajectory, "speeds", [])]
    force_mags = [round(float(f), 5) for f in getattr(trajectory, "force_mags", [])]
    gradient_mags = [round(float(g), 5) for g in getattr(trajectory, "gradient_mags", [])]

    return {
        "available": True,
        "total_steps": total_steps,
        "field_frames": field_frames,
        "movers": movers_data,
        "walls": walls_data,
        "active_gates": [int(g) for g in active_gates],
        "suppressed_gates": [int(g) for g in suppressed_gates],
        "gate_deposits": [int(g) for g in gate_deposits],
        "gate_switches": [int(g) for g in gate_switches],
        "speeds": speeds,
        "force_mags": force_mags,
        "gradient_mags": gradient_mags,
    }


def _parameter_spec_bounds(exp_id: str) -> dict[str, dict[str, Any]]:
    """Return parameter bounds from ParameterSpec for the given experiment."""
    if exp_id == "gated_movers":
        return {
            "gate_threshold": {"min": 0.0, "max": 1.0, "step": 0.01, "default": 0.5},
            "gate_cooldown": {"min": 0, "max": 20, "step": 1, "default": 4},
        }
    return {}


def _run_simulation(
    exp_id: str,
    params: dict[str, Any],
    max_steps: int,
    seed: int,
    *,
    tags: list[str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Run a simulation via the existing Alchemist executors, saving a durable ExperimentRecord."""
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

    world_copy = _replace(world, max_steps=max_steps, seed=seed)
    new_config = _copy.deepcopy(world_copy.config)
    new_config["n_steps"] = max_steps
    for k, v in params.items():
        new_config[k] = v
    world_copy = _replace(world_copy, config=new_config)

    start_time = time.perf_counter()
    executor_fn = executors[candidate.composition_id]
    outcome = executor_fn(world_copy)
    duration = time.perf_counter() - start_time

    det_run_id = run_id_of(world_copy)
    record_id = f"rec_{uuid.uuid4().hex[:12]}"
    template_name = candidate.template or "unknown"
    name_map = {
        "morphogenesis": "Morphogenesis (A)",
        "field_guided_movers": "Field-guided movers (B)",
        "adaptive_network": "Adaptive network (C)",
        "gated_movers": "Gated mover morphogenesis (D)",
    }

    serialized_traj = _serialize_trajectory(outcome.trajectory)

    # Check numerical health
    for k, v in outcome.metrics.items():
        if np.isnan(v) or np.isinf(v):
            error_msg = f"Numerical instability detected: metric '{k}' has non-finite value {v}"
            record = ExperimentRecord(
                record_id=record_id,
                run_id=det_run_id,
                composition_id=candidate.composition_id,
                experiment_template=template_name,
                experiment_name=name_map.get(template_name, template_name),
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                status="failed",
                execution_time_seconds=duration,
                seed=seed,
                max_steps=max_steps,
                parameters=params,
                canonical_world=world_copy.as_dict(),
                metrics=outcome.metrics,
                tags=tags or [],
                notes=notes,
                error_message=error_msg,
            )
            store.save_record(record, trajectory=serialized_traj)
            return {"record_id": record_id, "session_id": record_id, "outcome": outcome, "record": record}

    record = ExperimentRecord(
        record_id=record_id,
        run_id=det_run_id,
        composition_id=candidate.composition_id,
        experiment_template=template_name,
        experiment_name=name_map.get(template_name, template_name),
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status="completed",
        execution_time_seconds=duration,
        seed=seed,
        max_steps=max_steps,
        parameters=params,
        canonical_world=world_copy.as_dict(),
        metrics=outcome.metrics,
        tags=tags or [],
        notes=notes,
    )

    store.save_record(record, trajectory=serialized_traj)

    # Backward compatibility cache for legacy endpoints
    session_id = record_id
    _BACKEND_SESSIONS[session_id] = {
        "exp_id": exp_id,
        "candidate": candidate,
        "params": params,
        "max_steps": max_steps,
        "seed": seed,
        "outcome": outcome,
        "world": world_copy,
        "record": record,
    }

    return {"record_id": record_id, "session_id": session_id, "outcome": outcome, "record": record}


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
        raw_tags = data.get("tags")
        tags: list[str] = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else ([str(raw_tags)] if isinstance(raw_tags, str) and raw_tags else [])
        notes = str(data.get("notes") or "")

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

        for k, v in raw_params.items():
            if k not in clamped_params:
                clamped_params[k] = v

        result = _run_simulation(
            candidate.composition_id,
            clamped_params,
            max_steps,
            seed,
            tags=tags,
            notes=notes,
        )
        record_id = result["record_id"]
        session_id = result["session_id"]
        outcome = result["outcome"]
        record = result["record"]
        serialized_traj = _serialize_trajectory(outcome.trajectory)

        return jsonify({
            "record_id": record_id,
            "session_id": session_id,
            "run_id": record.run_id,
            "composition_id": record.composition_id,
            "status": record.status,
            "execution_time_seconds": record.execution_time_seconds,
            "outcome": {
                "metrics": outcome.metrics,
                "world_hash": run_id_of(outcome.world),
            },
            "outcome_metrics": outcome.metrics,
            "trajectory": serialized_traj,
        })
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Phase 2 REST APIs: History, Records, Replay, Compare, Export, Import
# ---------------------------------------------------------------------------

@app.get("/api/history")
def get_history() -> Any:
    """Retrieve filtered experiment history from persistent store."""
    template = request.args.get("template")
    status = request.args.get("status")
    tag = request.args.get("tag")
    search_q = request.args.get("q")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    records = store.list_records(
        experiment_template=template,
        status=status,
        tag=tag,
        search_query=search_q,
        limit=limit,
        offset=offset,
    )
    total = store.count_records(
        experiment_template=template,
        status=status,
        tag=tag,
    )

    return jsonify({
        "records": [r.as_dict() for r in records],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@app.get("/api/records/<record_id>")
def get_record_details(record_id: str) -> Any:
    """Fetch full details for an experiment record."""
    record = store.get_record(record_id)
    if record is None:
        return jsonify({"error": f"Record {record_id} not found"}), 404
    return jsonify(record.as_dict())


@app.get("/api/records/<record_id>/trajectory")
def get_record_trajectory(record_id: str) -> Any:
    """Fetch trajectory frames for a stored record."""
    traj = store.get_trajectory(record_id)
    if traj is None:
        return jsonify({"available": False, "error": f"No trajectory found for {record_id}"}), 404
    return jsonify(traj)


@app.patch("/api/records/<record_id>")
def update_record(record_id: str) -> Any:
    """Update notes or tags on an existing record."""
    data = request.get_json(force=True, silent=True) or {}
    notes = data.get("notes")
    tags = data.get("tags")

    updated = store.update_notes_and_tags(record_id, notes=notes, tags=tags)
    if not updated:
        return jsonify({"error": "Update failed or record not found"}), 404

    record = store.get_record(record_id)
    return jsonify({"success": True, "record": record.as_dict() if record else None})


@app.delete("/api/records/<record_id>")
def delete_record_route(record_id: str) -> Any:
    """Delete an experiment record and its trajectory."""
    deleted = store.delete_record(record_id)
    if not deleted:
        return jsonify({"error": "Record not found"}), 404
    return jsonify({"success": True, "deleted_record_id": record_id})


@app.post("/api/replay/<record_id>")
def replay_record(record_id: str) -> Any:
    """Deterministically re-run a stored experiment and verify zero metric drift."""
    record = store.get_record(record_id)
    if record is None:
        return jsonify({"error": f"Record {record_id} not found"}), 404

    try:
        from experiments.catalog import repository_executors
        from sim_alchemist.core.world import WorldDefinition

        exec_map = repository_executors()
        if record.composition_id not in exec_map:
            return jsonify({"error": f"Executor not registered for composition {record.composition_id}"}), 400

        # Reconstruct WorldDefinition
        world = WorldDefinition.from_dict(record.canonical_world)
        replayed_outcome = exec_map[record.composition_id](world)

        original_metrics = record.metrics
        replayed_metrics = replayed_outcome.metrics

        # Compute max delta across float metrics
        max_delta = 0.0
        metric_deltas: dict[str, float] = {}
        all_keys = set(list(original_metrics.keys()) + list(replayed_metrics.keys()))
        for k in all_keys:
            orig_v = float(original_metrics.get(k, 0.0))
            rep_v = float(replayed_metrics.get(k, 0.0))
            d = abs(rep_v - orig_v)
            metric_deltas[k] = d
            max_delta = max(max_delta, d)

        replayed_run_id = run_id_of(world)
        is_identical = (replayed_run_id == record.run_id) and (max_delta < 1e-7)

        return jsonify({
            "record_id": record_id,
            "original_run_id": record.run_id,
            "replayed_run_id": replayed_run_id,
            "is_identical": is_identical,
            "max_metric_delta": max_delta,
            "original_metrics": original_metrics,
            "replayed_metrics": replayed_metrics,
            "metric_deltas": metric_deltas,
            "trajectory": _serialize_trajectory(replayed_outcome.trajectory),
        })
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Replay failed: {e}"}), 500


@app.post("/api/compare")
def compare_runs() -> Any:
    """Compare any two experiment records (or compute D ON vs OFF)."""
    data = request.get_json(force=True, silent=True) or {}
    record_id_a = data.get("record_id_a")
    record_id_b = data.get("record_id_b")

    if not record_id_a or not record_id_b:
        return jsonify({"error": "Missing record_id_a or record_id_b"}), 400

    rec_a = store.get_record(record_id_a)
    rec_b = store.get_record(record_id_b)

    if not rec_a:
        return jsonify({"error": f"Record A ({record_id_a}) not found"}), 404
    if not rec_b:
        return jsonify({"error": f"Record B ({record_id_b}) not found"}), 404

    traj_a = store.get_trajectory(record_id_a)
    traj_b = store.get_trajectory(record_id_b)

    # Compute parameter diffs
    param_diffs: list[dict[str, Any]] = []
    all_param_keys = sorted(set(list(rec_a.parameters.keys()) + list(rec_b.parameters.keys())))
    for pk in all_param_keys:
        va = rec_a.parameters.get(pk)
        vb = rec_b.parameters.get(pk)
        param_diffs.append({
            "parameter": pk,
            "val_a": va,
            "val_b": vb,
            "is_different": va != vb,
        })

    # Include seed & max_steps in param diff if different
    if rec_a.seed != rec_b.seed:
        param_diffs.append({"parameter": "seed", "val_a": rec_a.seed, "val_b": rec_b.seed, "is_different": True})
    if rec_a.max_steps != rec_b.max_steps:
        param_diffs.append({"parameter": "max_steps", "val_a": rec_a.max_steps, "val_b": rec_b.max_steps, "is_different": True})

    # Compute metric deltas
    metric_diffs: list[dict[str, Any]] = []
    all_metric_keys = sorted(set(list(rec_a.metrics.keys()) + list(rec_b.metrics.keys())))
    for mk in all_metric_keys:
        in_a = mk in rec_a.metrics
        in_b = mk in rec_b.metrics
        ma = rec_a.metrics.get(mk)
        mb = rec_b.metrics.get(mk)
        delta = (mb - ma) if (ma is not None and mb is not None) else None
        metric_diffs.append({
            "metric": mk,
            "val_a": ma,
            "val_b": mb,
            "delta": delta,
            "available_in_both": in_a and in_b,
        })

    return jsonify({
        "run_a": {
            "record_id": rec_a.record_id,
            "run_id": rec_a.run_id,
            "experiment_name": rec_a.experiment_name,
            "template": rec_a.experiment_template,
            "parameters": rec_a.parameters,
            "seed": rec_a.seed,
            "max_steps": rec_a.max_steps,
        },
        "run_b": {
            "record_id": rec_b.record_id,
            "run_id": rec_b.run_id,
            "experiment_name": rec_b.experiment_name,
            "template": rec_b.experiment_template,
            "parameters": rec_b.parameters,
            "seed": rec_b.seed,
            "max_steps": rec_b.max_steps,
        },
        "parameter_diffs": param_diffs,
        "metric_diffs": metric_diffs,
        "trajectory_a": traj_a,
        "trajectory_b": traj_b,
    })


@app.get("/comparison")
def comparison() -> Any:
    """Compare D gating ON vs OFF using real simulation data (Preserves Phase 1.5.1 behavior)."""
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

    # Run with threshold ON (0.5)
    world_on = _replace(d_candidate.generated_world, max_steps=12, seed=42)
    new_config = _copy.deepcopy(world_on.config)
    new_config["n_steps"] = 12
    new_config["gate_threshold"] = 0.5
    new_config["gate_cooldown"] = 4
    world_on_copy = _replace(world_on, max_steps=12, config=new_config)

    from experiments.catalog import repository_executors as _executors

    exec_map = _executors()
    outcome_on = exec_map[comp_id](world_on_copy)

    # Run with threshold OFF (0.0)
    world_off = _replace(d_candidate.generated_world, max_steps=12, seed=42)
    new_config2 = _copy.deepcopy(world_off.config)
    new_config2["n_steps"] = 12
    new_config2["gate_threshold"] = 0.0
    new_config2["gate_cooldown"] = 0
    world_off_copy = _replace(world_off, max_steps=12, config=new_config2)

    outcome_off = exec_map[comp_id](world_off_copy)

    # Compute real metric deltas
    on_metrics = outcome_on.metrics
    off_metrics = outcome_off.metrics

    diff: dict[str, Any] = {}
    all_keys = set(list(on_metrics.keys()) + list(off_metrics.keys()))
    for key in sorted(all_keys):
        on_val = on_metrics.get(key, 0)
        off_val = off_metrics.get(key, 0)
        delta = off_val - on_val
        diff[key] = {"on": on_val, "off": off_val, "delta": delta}

    # Save to persistent store as well
    rec_on = ExperimentRecord(
        record_id=f"rec_d_on_{uuid.uuid4().hex[:8]}",
        run_id=run_id_of(outcome_on.world),
        composition_id=comp_id,
        experiment_template="gated_movers",
        experiment_name="Gated mover morphogenesis (D) [ON]",
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status="completed",
        execution_time_seconds=0.5,
        seed=42,
        max_steps=12,
        parameters={"gate_threshold": 0.5, "gate_cooldown": 4},
        canonical_world=world_on_copy.as_dict(),
        metrics=outcome_on.metrics,
        tags=["comparison", "gating_on"],
    )
    store.save_record(rec_on, _serialize_trajectory(outcome_on.trajectory))

    rec_off = ExperimentRecord(
        record_id=f"rec_d_off_{uuid.uuid4().hex[:8]}",
        run_id=run_id_of(outcome_off.world),
        composition_id=comp_id,
        experiment_template="gated_movers",
        experiment_name="Gated mover morphogenesis (D) [OFF]",
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status="completed",
        execution_time_seconds=0.5,
        seed=42,
        max_steps=12,
        parameters={"gate_threshold": 0.0, "gate_cooldown": 0},
        canonical_world=world_off_copy.as_dict(),
        metrics=outcome_off.metrics,
        tags=["comparison", "gating_off"],
    )
    store.save_record(rec_off, _serialize_trajectory(outcome_off.trajectory))

    return jsonify({
        "diff": diff,
        "on_trajectory": _serialize_trajectory(outcome_on.trajectory),
        "off_trajectory": _serialize_trajectory(outcome_off.trajectory),
        "provenance": {
            "on_record_id": rec_on.record_id,
            "off_record_id": rec_off.record_id,
            "on_run_id": run_id_of(outcome_on.world),
            "off_run_id": run_id_of(outcome_off.world),
            "on_config": {"gate_threshold": 0.5, "gate_cooldown": 4, "max_steps": 12},
            "off_config": {"gate_threshold": 0.0, "gate_cooldown": 0, "max_steps": 12},
            "experiment": d_candidate.template,
            "comparison_type": "gating_ON_vs_OFF",
        },
    })


@app.get("/export/<id_str>")
def export_endpoint(id_str: str) -> Any:
    """Three-tier export endpoint supporting Level 1, 2, and 3."""
    level = int(request.args.get("level", 2))
    record = store.get_record(id_str)

    # Check fallback session cache
    if record is None and id_str in _BACKEND_SESSIONS:
        sess = _BACKEND_SESSIONS[id_str]
        record = sess.get("record")

    if record is None:
        return jsonify({"error": f"Record {id_str} not found"}), 404

    if level == 1:
        content = export_result_json(record)
        return Response(
            content,
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment;filename=sim_alch_result_{record.record_id}.json"},
        )
    if level == 3:
        traj = store.get_trajectory(record.record_id)
        zip_bytes = export_trajectory_archive(record, traj)
        return send_file(
            io.BytesIO(zip_bytes),
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"sim_alch_archive_{record.record_id}.zip",
        )

    # Default Level 2: Reproducible Record
    content = export_reproducible_record(record)
    return Response(
        content,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment;filename=sim_alch_record_{record.record_id}.simrec"},
    )


@app.post("/api/import")
def import_record_route() -> Any:
    """Import and validate a Level 2 reproducible experiment record (.simrec)."""
    try:
        raw_content = None
        if "file" in request.files:
            file_obj = request.files["file"]
            raw_content = file_obj.read().decode("utf-8")
        else:
            raw_content = request.get_data(as_text=True)

        if not raw_content:
            return jsonify({"error": "No file or payload provided"}), 400

        parsed = import_reproducible_record(raw_content)
        return jsonify({
            "valid": True,
            "record_spec": parsed,
        })
    except Exception as e:  # noqa: BLE001
        return jsonify({"valid": False, "error": str(e)}), 400


# ---------------------------------------------------------------------------
# Phase 3 Discovery & Automation Endpoints
# ---------------------------------------------------------------------------
@app.post("/api/discovery/run")
def api_discovery_run() -> Any:
    """Execute a bounded parameter discovery pass."""
    data = request.get_json(force=True) or {}
    template_name = str(data.get("experiment_template", "gated_movers"))
    sweeps_data = data.get("sweeps")
    max_steps = int(data.get("max_steps", 12))
    seed = int(data.get("seed", 42))
    beam_width = int(data.get("beam_width", 3))
    quality_weight = float(data.get("quality_weight", 0.7))
    diversity_weight = float(data.get("diversity_weight", 0.3))
    session_name = str(data.get("session_name", ""))
    notes = str(data.get("notes", ""))

    try:
        pass_result = run_discovery_pass(
            template_name,
            sweeps_data,
            beam_width=beam_width,
            quality_weight=quality_weight,
            diversity_weight=diversity_weight,
            max_steps=max_steps,
            seed=seed,
            session_name=session_name,
            notes=notes,
            store=store,
        )
        return jsonify({
            "success": True,
            "result": pass_result.as_dict(),
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"success": False, "error": f"Discovery pass failed: {e}"}), 500


@app.get("/api/discovery/specs/<template_name>")
def api_discovery_specs(template_name: str) -> Any:
    """Retrieve declared ParameterSpecs and default MutationSpace for an experiment."""
    try:
        specs = get_experiment_parameter_specs(template_name)
        specs_dict = {
            k: {
                "path": s.path,
                "description": s.description,
                "minimum": s.minimum,
                "maximum": s.maximum,
            }
            for k, s in specs.items()
        }
        default_space = get_default_mutation_space(template_name)
        default_sweeps = [d.to_dict() for d in default_space.dimensions]
        runtime_est = estimate_discovery_runtime(template_name, default_space.variant_count, 12)
        return jsonify({
            "success": True,
            "template": template_name,
            "specs": specs_dict,
            "default_sweeps": default_sweeps,
            "default_variant_count": default_space.variant_count,
            "estimated_runtime_seconds": runtime_est,
        })
    except Exception as e:  # noqa: BLE001
        return jsonify({"success": False, "error": str(e)}), 400


@app.get("/api/discovery/sessions")
def api_discovery_sessions() -> Any:
    """List historical discovery sessions."""
    try:
        template = request.args.get("experiment_template")
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        sessions = store.list_discovery_sessions(experiment_template=template, limit=limit, offset=offset)
        return jsonify({
            "success": True,
            "sessions": [s.as_dict() for s in sessions],
        })
    except Exception as e:  # noqa: BLE001
        return jsonify({"success": False, "error": str(e)}), 500


@app.get("/api/discovery/sessions/<session_id>")
def api_discovery_session_detail(session_id: str) -> Any:
    """Retrieve full details and candidate records of a discovery session."""
    session = store.get_discovery_session(session_id)
    if session is None:
        return jsonify({"success": False, "error": f"Session '{session_id}' not found"}), 404

    candidate_records = []
    for rid in session.candidate_record_ids:
        rec = store.get_record(rid)
        if rec is not None:
            candidate_records.append(rec.as_dict())

    return jsonify({
        "success": True,
        "session": session.as_dict(),
        "candidates": candidate_records,
    })


@app.delete("/api/discovery/sessions/<session_id>")
def api_discovery_session_delete(session_id: str) -> Any:
    """Delete a discovery session."""
    deleted = store.delete_discovery_session(session_id)
    if not deleted:
        return jsonify({"success": False, "error": f"Session '{session_id}' not found"}), 404
    return jsonify({"success": True, "session_id": session_id})


def main() -> None:
    """Run the Flask workbench."""
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()