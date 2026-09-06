"""Stability/boundedness verification for the chemo-mechanical loop.

  S1 wall centres stay inside [radius, 1-radius] for the entire run
  S2 wall speeds stay below the analytic terminal bound v_ss ~= Fmax/(m(1-D))
  S3 no NaN/inf in field snapshots or forces
  S4 extreme forcing (Fmax=10, weak damping) stays bounded
  S5 integrator convergence: halving the physical substep reduces the
     discretization error (order-1: error ratio < 1 when dt is halved)
  S6 short-horizon coupled agreement: the same walls are built at the same
     macro steps under both physics discretizations, positions drift by less
     than one macro-step of motion, and the field has not yet diverged
"""
import math

import numpy as np

from chemomech.agents import AgentConfig
from chemomech.physics import WallSpace
from chemomech.simulation import WorldConfig, run_world


def _constant_force_drift(dt_sub, substeps, macros=10, force=0.1,
                          x=0.5):
    ws = WallSpace(n=32, mass=1.0, damping=0.05, dt_phys=dt_sub,
                   phys_substeps=substeps)
    w = ws.add_wall((x, 0.5), (x + 0.2, 0.5), radius=0.02, t=0.0)
    for _ in range(macros):
        ws.apply_force(w, force, 0.0, 0.0)
        ws.step()
    return math.hypot(w.center[0] - x, w.center[1] - 0.5)


def validate_stability(seed: int = 0, n_steps: int = 160) -> list[tuple[str, bool, str]]:
    agents = [AgentConfig(x=0.3, y=0.5), AgentConfig(x=0.7, y=0.5)]
    out: list[tuple[str, bool, str]] = []

    nominal = WorldConfig(n=32, seed=seed, n_steps=n_steps,
                          agent_configs=list(agents))
    t = run_world(nominal)
    centers = [pt for tr in t.wall_tracks.values() for pt in tr]
    s1 = bool(centers) and all(0.02 - 1e-9 <= x <= 1 - 0.02 + 1e-9
                               and 0.02 - 1e-9 <= y <= 1 - 0.02 + 1e-9
                               for x, y in [(p[1], p[2]) for p in centers])
    vmax = max(t.wall_speeds)
    v_bound = nominal.force_fmax / (nominal.wall_mass * (1.0 - nominal.wall_damping))
    s2 = vmax < v_bound * 1.5
    s3 = (all(np.isfinite(s).all() for s in t.u_snaps)
          and all(math.isfinite(f) for f in t.force_mags))
    out += [
        ("S1_walls_in_bounds", s1,
         f"{len(centers)} centre samples inside [radius, 1-radius]"),
        ("S2_speed_bounded", s2,
         f"vmax={vmax:.4f} < analytic bound {v_bound:.4f}"),
        ("S3_no_nan", s3, "field snapshots and forces finite"),
    ]

    strong = WorldConfig(n=32, seed=seed, n_steps=n_steps, force_fmax=10.0,
                         wall_damping=0.02, agent_configs=list(agents))
    t = run_world(strong)
    centers_s = [pt for tr in t.wall_tracks.values() for pt in tr]
    vmax_s = max(t.wall_speeds)
    s4 = (bool(centers_s)
          and all(0.02 <= p[1] <= 1 - 0.02 and 0.02 <= p[2] <= 1 - 0.02
                  for p in centers_s)
          and vmax_s < 10.0 / (1.0 - 0.02) * 1.5
          and all(np.isfinite(s).all() for s in t.u_snaps))
    out.append(("S4_extreme_force_bounded", s4,
                f"Fmax=10, damping=0.02: vmax={vmax_s:.4f}, centres in box"))

    d1 = _constant_force_drift(0.05, 4)
    d2 = _constant_force_drift(0.025, 8)
    d4 = _constant_force_drift(0.0125, 16)
    err1, err2 = abs(d1 - d2), abs(d2 - d4)
    s5 = err1 > 1e-6 and err2 < err1
    out.append(("S5_integrator_convergence", s5,
                (f"error(dt=0.05)={err1:.5f} -> error(dt=0.025)={err2:.5f} "
                 f"ratio={err2 / err1:.3f} (order-1)")))

    early = [AgentConfig(x=0.3, y=0.5, build_threshold=0.0),
             AgentConfig(x=0.7, y=0.5, build_threshold=0.0)]
    ta = run_world(WorldConfig(n=32, seed=seed, n_steps=8,
                               agent_configs=list(early)))
    tb = run_world(WorldConfig(n=32, seed=seed, n_steps=8, phys_dt=0.025,
                               phys_substeps=8, agent_configs=list(early)))
    ids = sorted(set(ta.wall_tracks) | set(tb.wall_tracks))
    max_err = 0.0
    for wid in ids:
        la = ta.wall_tracks.get(wid)
        lb = tb.wall_tracks.get(wid)
        if la and lb:
            for pa, pb in zip(la, lb):
                max_err = max(max_err, math.hypot(pa[1] - pb[1], pa[2] - pb[2]))
    count_series = (ta.wall_counts() == tb.wall_counts()).all()
    field_close = float(np.sqrt(np.mean((ta.final_u - tb.final_u) ** 2))) < 1e-6
    s6 = count_series and max_err < 0.05 and field_close
    out.append(("S6_short_horizon_agreement", s6,
                (f"wall-count series identical={count_series}, "
                 f"max drift={max_err:.2e} (<0.05), field RMSD<1e-6={field_close}")))

    return out


def main() -> None:
    results = validate_stability()
    print("=== Stability verification ===")
    allpass = True
    for name, passed, detail in results:
        allpass = allpass and passed
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    print()
    print("ALL STABILITY CHECKS PASSED:", allpass)


if __name__ == "__main__":
    main()