"""Task 0.3 validation experiments A-G plus metrics and figures.

Runs (shared seed, so the only variation is the mechanism):

  E1 baseline   build_walls=False,  forces off -> Turing pattern, no walls
  E2 static     build_walls=True,   forces OFF  -> Task 0.2 clamped-obstacle behaviour
  E3 dynamic    build_walls=True,   forces ON   -> full chemo-mechanical loop
  E4 replay     E3 run a second time           -> determinism check
  E5 machine    WallSpace alone, constant force -> mechanical response test

Validations:
  A  static  : Task 0.2 behaviour is reproduced (fixed geometry, mask, pattern)
  B  dynamic : walls physically MOVE (pymunk integration under body forces)
  C  geometry: the PDE mask changes when wall geometry changes
  D  field   : the morphogen field differs between dynamic and static runs
  E  agents  : agent decision logs differ between dynamic and static runs
  F  loop    : closed loop is active (motion + decisions + field all coupled)
  G  replay  : two identical-seed runs are bitwise identical end to end

Figures (exact task-mandated filenames):
  01_baseline_turing.png       baseline morphogen pattern (A)
  02_static_wall_coupling.png  static walls + blocked cells + field (A/C)
  03_dynamic_wall_coupling.png dynamic walls + trajectories + field (B,D,F)
  04_wall_trajectory.png       every wall's centre-of-mass path (B,F)
  05_feedback_metrics.png      walls, force, speed, decisions time series (F)
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .agents import AgentConfig
from .physics import WallSpace
from .simulation import Trajectory, WorldConfig, run_world

FIGDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "figures")


def build_agents() -> list[AgentConfig]:
    return [
        AgentConfig(x=0.3, y=0.5),
        AgentConfig(x=0.7, y=0.5),
    ]


@dataclass
class ValidationResult:
    name: str
    passed: bool
    detail: str
    metrics: dict[str, float] = field(default_factory=dict)
    data: dict = field(default_factory=dict)


def normalized_rmsd(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean((a - b) ** 2)) / (np.std(b) + 1e-12))


def field_correlation(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.corrcoef(a.ravel(), b.ravel())[0, 1])


def run_experiments(base_cfg: WorldConfig) -> dict[str, Trajectory]:
    agents = build_agents()

    baseline = WorldConfig(**{**base_cfg.__dict__, "build_walls": False,
                              "feedback": False, "apply_forces": False,
                              "agent_configs": agents})
    static = WorldConfig(**{**base_cfg.__dict__, "build_walls": True,
                            "feedback": True, "apply_forces": False,
                            "agent_configs": agents})
    dynamic = WorldConfig(**{**base_cfg.__dict__, "build_walls": True,
                             "feedback": True, "apply_forces": True,
                             "agent_configs": agents})

    return {
        "baseline": run_world(baseline),
        "static": run_world(static),
        "dynamic": run_world(dynamic),
        "replay": run_world(dynamic),
    }


def decisions_differ(a: Trajectory, b: Trajectory) -> int:
    """Count differing decision-log entries (built / dissolved / sensed gmag)."""
    ndiff = 0
    n_agents = max(len(a.agent_histories), len(b.agent_histories))
    for i in range(n_agents):
        ha, hb = a.decisions(i), b.decisions(i)
        for k in range(min(len(ha), len(hb))):
            if ha[k]["built"] != hb[k]["built"]:
                ndiff += 1
            if ha[k]["dissolved"] != hb[k]["dissolved"]:
                ndiff += 1
            if abs(ha[k]["gmag"] - hb[k]["gmag"]) > 1e-9:
                ndiff += 1
    return ndiff


def wall_net_displacements(traj: Trajectory) -> dict[int, float]:
    out = {}
    for wid, track in traj.wall_tracks.items():
        start = track[0]
        end = track[-1]
        out[wid] = math.hypot(end[1] - start[1], end[2] - start[2])
    return out


def wall_total_path(traj: Trajectory) -> float:
    total = 0.0
    for track in traj.wall_tracks.values():
        for k in range(1, len(track)):
            total += math.hypot(track[k][1] - track[k - 1][1],
                                track[k][2] - track[k - 1][2])
    return total


def mask_drift_count(traj: Trajectory) -> int:
    """Number of blocked-cell flips across consecutive macro steps."""
    total = 0
    for k in range(1, len(traj.blocked_snaps)):
        total += int(np.count_nonzero(
            traj.blocked_snaps[k] != traj.blocked_snaps[k - 1]
        ))
    return total


def mechanical_response_test() -> tuple[float, bool]:
    """Drive a single wall with a constant force; confirm pymunk moves it."""
    ws = WallSpace(n=32, mass=1.0, damping=0.05, dt_phys=0.05, phys_substeps=4)
    w = ws.add_wall((0.5, 0.5), (0.7, 0.5), radius=0.02, t=0.0)
    m0 = ws.blocked().copy()
    for _ in range(20):
        ws.apply_force(w, 0.8, 0.0, 0.0)
        ws.step()
    moved = math.hypot(w.center[0] - 0.5, w.center[1] - 0.5)
    mask_changed = not np.array_equal(m0, ws.blocked())
    return moved, mask_changed


# ----------------------------------------------------------------------
# figures
# ----------------------------------------------------------------------
def _plot_field(ax, traj: Trajectory, title: str,
                blocked=None, segments=None):
    im = ax.imshow(traj.final_u.T, origin="lower", extent=[0, 1, 0, 1],
                   cmap="magma", interpolation="nearest")
    if blocked is not None and blocked.any():
        ax.contour(blocked.T, levels=[0.5], colors="lime", linewidths=1.5,
                   extent=[0, 1, 0, 1])
    if segments:
        for (p1, p2, radius) in segments:
            ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color="cyan", lw=2.0)
    ax.set_title(title)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    return im


def _make_figures(results: dict[str, Trajectory]) -> list[str]:
    os.makedirs(FIGDIR, exist_ok=True)
    paths = []
    base, stat, dyn = results["baseline"], results["static"], results["dynamic"]

    # 01 baseline Turing pattern (A)
    fig, ax = plt.subplots(1, 1, figsize=(5, 4.6))
    im = _plot_field(ax, base, "01: baseline morphogen u (no walls)")
    fig.colorbar(im, ax=ax, fraction=0.045)
    fig.tight_layout()
    p = os.path.join(FIGDIR, "01_baseline_turing.png")
    fig.savefig(p, dpi=110); plt.close(fig); paths.append(p)

    # 02 static wall coupling (A, C): geometry frozen -> clamped obstacles
    fig, ax = plt.subplots(1, 1, figsize=(5, 4.6))
    im = _plot_field(ax, stat, "02: static walls (Task 0.2 clamped obstacles)",
                     blocked=stat.final_blocked, segments=stat.wall_geometry_snaps[-1])
    fig.colorbar(im, ax=ax, fraction=0.045)
    fig.tight_layout()
    p = os.path.join(FIGDIR, "02_static_wall_coupling.png")
    fig.savefig(p, dpi=110); plt.close(fig); paths.append(p)

    # 03 dynamic wall coupling (B, D, F): walls move with the field
    fig, ax = plt.subplots(1, 1, figsize=(5, 4.6))
    for i, track in enumerate(dyn.wall_tracks.values()):
        xs = [pt[1] for pt in track]
        ys = [pt[2] for pt in track]
        ax.plot(xs, ys, color="0.55", lw=0.7, alpha=0.6, zorder=1)
    im = _plot_field(ax, dyn, "03: dynamic walls (chemo-mechanical loop)",
                     blocked=dyn.final_blocked, segments=dyn.wall_geometry_snaps[-1])
    fig.colorbar(im, ax=ax, fraction=0.045)
    fig.tight_layout()
    p = os.path.join(FIGDIR, "03_dynamic_wall_coupling.png")
    fig.savefig(p, dpi=110); plt.close(fig); paths.append(p)

    # 04 wall trajectories (B, F): centre-of-mass paths, creation marked
    fig, ax = plt.subplots(1, 1, figsize=(5, 5))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.set_title("04: wall centre-of-mass trajectories")
    ax.set_xlabel("x"); ax.set_ylabel("y")
    cmap = plt.get_cmap("tab10")
    for i, (wid, track) in enumerate(dyn.wall_tracks.items()):
        col = cmap(i % 10)
        xs = [pt[1] for pt in track]
        ys = [pt[2] for pt in track]
        ax.plot(xs, ys, color=col, lw=1.1, alpha=0.85)
        ax.plot(xs[0], ys[0], marker="o", ms=4, color=col, zorder=5)
    fig.tight_layout()
    p = os.path.join(FIGDIR, "04_wall_trajectory.png")
    fig.savefig(p, dpi=110); plt.close(fig); paths.append(p)

    # 05 feedback metrics (F): walls, speed/force, decisions, cumulative motion
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    tc = dyn.t_field
    stc = stat.t_field

    axes[0, 0].plot(stc, stat.wall_counts(), lw=1.4, label="static (no forces)")
    axes[0, 0].plot(tc, dyn.wall_counts(), lw=1.4, label="dynamic (forces)")
    axes[0, 0].set_title("wall count over time")
    axes[0, 0].legend(fontsize=8)

    axes[0, 1].plot(tc, dyn.force_mags, lw=1.2, color="tab:red", label="mean |F|")
    ax2 = axes[0, 1].twinx()
    ax2.plot(tc, dyn.wall_speeds, lw=1.2, color="tab:blue", ls="--",
             label="mean wall speed")
    axes[0, 1].set_title("mechanical forcing (dynamic)")
    axes[0, 1].set_ylabel("|F|")
    ax2.set_ylabel("speed")
    axes[0, 1].legend(fontsize=8, loc="upper left")
    ax2.legend(fontsize=8, loc="upper right")

    for i in range(2):
        gd = [h["gmag"] for h in dyn.decisions(i)]
        gs = [h["gmag"] for h in stat.decisions(i)]
        ax = axes[1, i]
        ax.plot(tc[:len(gd)], gd, lw=1.0, label="dynamic",
                color="tab:green")
        ax.plot(stc[:len(gs)], gs, lw=1.0, ls="--", label="static (no forces)",
                color="tab:orange")
        ax.axhline(dyn.config.agent_configs[i].build_threshold,
                   color="r", lw=0.6, ls=":")
        ax.set_title(f"agent {i}: sensed |grad u|")
        ax.legend(fontsize=8)
        ax.set_xlabel("field time t")

    fig.suptitle("05: closed-loop feedback metrics (dynamic vs static)",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    p = os.path.join(FIGDIR, "05_feedback_metrics.png")
    fig.savefig(p, dpi=110); plt.close(fig); paths.append(p)

    return paths


# ----------------------------------------------------------------------
# validation
# ----------------------------------------------------------------------
def validate(base_cfg: WorldConfig | None = None) -> list[ValidationResult]:
    if base_cfg is None:
        base_cfg = WorldConfig(n=32, seed=0, n_steps=160)
    print("running experiments (4 world runs + 1 mechanical machine test)...")
    results = run_experiments(base_cfg)

    base, stat, dyn, replay = (
        results["baseline"], results["static"],
        results["dynamic"], results["replay"],
    )
    r: list[ValidationResult] = []

    # A: static baseline reproduces Task 0.2 clamped-obstacle behaviour
    a_std = float(stat.final_u.std())
    a_walls = int(stat.walls_per_step[-1])
    a_blocked = int(np.count_nonzero(stat.final_blocked))
    a_rmse = normalized_rmsd(stat.final_u, base.final_u)
    r.append(ValidationResult(
        name="A_static_reproduces_0.2",
        passed=(a_std > 0.2) and (a_walls > 0) and (a_blocked > 0) and (a_rmse > 0.1),
        detail=(f"static run: u std={a_std:.3f}, walls={a_walls}, "
                f"blocked cells={a_blocked}, norm RMSD vs baseline={a_rmse:.3f}"),
        metrics={"u_std": a_std, "walls": a_walls, "blocked_cells": a_blocked,
                 "norm_rmsd_vs_baseline": a_rmse},
    ))

    # B: mechanical response -- pymunk integrates wall motion under force
    moved_micro, mask_changed_micro = mechanical_response_test()
    dyn_disp = wall_net_displacements(dyn)
    max_disp = max(dyn_disp.values()) if dyn_disp else 0.0
    n_moved = int(sum(1 for d in dyn_disp.values() if d > 1e-3))
    r.append(ValidationResult(
        name="B_mechanical_response",
        passed=(moved_micro > 0.01) and (n_moved >= 1),
        detail=(f"constant-force wall moved {moved_micro:.3f} DU; dynamic run has "
                f"{n_moved}/{len(dyn_disp)} walls with net motion >1e-3 "
                f"(max {max_disp:.3f})"),
        metrics={"machine_moved": moved_micro, "n_moved": n_moved,
                 "max_net_displacement": max_disp},
    ))

    # C: geometry feedback -- mask tracks wall motion
    drift = mask_drift_count(dyn)
    r.append(ValidationResult(
        name="C_geometry_feedback",
        passed=mask_changed_micro and (drift > 0),
        detail=(f"machine test: mask changed after motion={mask_changed_micro}; "
                f"dynamic run blocked-cell flips across macro steps={drift}"),
        metrics={"blocked_cell_flips": drift},
    ))

    # D: field feedback -- dynamics change the morphogen field
    d_rmse = normalized_rmsd(dyn.final_u, stat.final_u)
    d_corr = field_correlation(dyn.final_u, stat.final_u)
    r.append(ValidationResult(
        name="D_field_feedback",
        passed=(d_rmse > 0.1) and (d_corr < 0.999),
        detail=(f"dynamic vs static final u: norm RMSD={d_rmse:.3f}, "
                f"correlation={d_corr:.4f}"),
        metrics={"norm_rmsd": d_rmse, "correlation": d_corr},
    ))

    # E: agents feel the difference
    e_diff = decisions_differ(dyn, stat)
    r.append(ValidationResult(
        name="E_agent_feedback",
        passed=e_diff > 0,
        detail=f"dynamic vs static decision logs differ in {e_diff} entries",
        metrics={"differing_decision_entries": e_diff},
    ))

    # F: closed loop active everywhere (motion + mask + field + decisions)
    path_sum = wall_total_path(dyn)
    r.append(ValidationResult(
        name="F_closed_loop",
        passed=(max_disp > 1e-3) and (drift > 0) and (d_rmse > 0.1) and (e_diff > 0),
        detail=(f"loop active: total wall path={path_sum:.3f} DU over "
                f"{len(dyn.walls_per_step)} macro steps, dissolved={int(dyn.dissolved_count[-1])}"),
        metrics={"total_wall_path": path_sum, "dissolved": int(dyn.dissolved_count[-1])},
    ))

    # G: determinism -- identical seed, identical outcome, bit for bit
    g_field = np.array_equal(dyn.final_u, replay.final_u)
    g_tracks = dyn.wall_tracks == replay.wall_tracks
    g_forces = dyn.force_mags == replay.force_mags
    g_speeds = dyn.wall_speeds == replay.wall_speeds
    g_decisions = all(
        [(h["built"], h["dissolved"], round(h["gmag"], 12)) ==
         (hr["built"], hr["dissolved"], round(hr["gmag"], 12))
         for h, hr in zip(dyn.decisions(i), replay.decisions(i))]
        for i in range(len(dyn.agent_histories))
    )
    g_ok = g_field and g_tracks and g_forces and g_speeds and g_decisions
    r.append(ValidationResult(
        name="G_determinism",
        passed=g_ok,
        detail=(f"replay bitwise identical: field={g_field}, tracks={g_tracks}, "
                f"forces={g_forces}, speeds={g_speeds}, decisions={g_decisions}"),
        metrics={"field_identical": float(g_field)},
    ))

    try:
        figure_paths = _make_figures(results)
        for fp in figure_paths:
            print("figure:", fp)
    except Exception as exc:  # noqa: BLE001 - plotting must never break validation
        print("figure generation failed:", exc)

    return r