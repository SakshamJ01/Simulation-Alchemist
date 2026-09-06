"""Run the Field-Guided Movers experiment and visualize the feedback loop.

Usage (project root):

    python -m experiments.field_guided_movers.run [--steps N] [--seed S]
        [--open-loop] [--figures-dir figures]

Runs the closed-loop composed world, prints summary metrics, and writes a
matplotlib figure showing:
  * the final activator field with mover start (dot) and end (arrow/x)
    positions and their trajectories;
  * the closed-loop vs open-loop activator divergence produced by the
    movers' chemical deposition.
"""

from __future__ import annotations

import argparse
import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from .model import MoversConfig, run_field_guided_movers


def _arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Field-Guided Movers (Task 1.1)")
    parser.add_argument("--steps", type=int, default=None, help="macro steps")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed")
    parser.add_argument("--open-loop", action="store_true",
                        help="disable mover source injection (open-loop control)")
    parser.add_argument("--figures-dir", default="figures")
    return parser


def summarize(name: str, traj) -> None:
    disp = traj.net_displacements()
    paths = traj.total_paths()
    print(f"[{name}]")
    print(f"  steps={len(traj.t_field)}  final_u.std={float(traj.final_u.std()):.4f}")
    print(f"  mean|F|={float(np.mean(traj.force_mags)):.4f}  "
          f"mean speed={float(np.mean(traj.speeds)):.4f}  "
          f"mean|grad u|={float(np.mean(traj.gradient_mags)):.4f}")
    for mover_id in sorted(disp):
        print(f"  mover {mover_id}: net displacement={disp[mover_id]:.4f}  "
              f"total path={paths[mover_id]:.4f}")


def plot(closed, open_loop, out_path: str) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    ax = axes[0]
    im = ax.imshow(closed.final_u.T, origin="lower", cmap="viridis", aspect="equal",
                   extent=(0, 1, 0, 1))
    for pts in closed.positions.values():
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, color="white", linewidth=0.8, alpha=0.8)
        ax.plot(xs[0], ys[0], "o", color="white", markersize=6)
        ax.plot(xs[-1], ys[-1], "x", color="red", markersize=8)
    ax.set_title("Final activator field + mover trajectories (closed loop)")
    ax.set_xlabel("x"); ax.set_ylabel("y")
    fig.colorbar(im, ax=ax, fraction=0.046)

    ax = axes[1]
    diff = closed.final_u - open_loop.final_u
    im2 = ax.imshow(diff.T, origin="lower", cmap="coolwarm", aspect="equal",
                    extent=(0, 1, 0, 1))
    ax.set_title("Field change caused by movers (closed - open loop)")
    ax.set_xlabel("x"); ax.set_ylabel("y")
    fig.colorbar(im2, ax=ax, fraction=0.046)
    fig.suptitle("Task 1.1 - Field-Guided Movers (py-pde + Pymunk, no Mesa)")
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"saved: {out_path}")


def main() -> None:
    args = _arg_parser().parse_args()
    cfg = MoversConfig()
    if args.steps is not None:
        cfg.n_steps = args.steps
    if args.seed is not None:
        cfg.seed = args.seed
    if args.open_loop:
        cfg.apply_sources = False

    closed_cfg = MoversConfig(**cfg.as_dict())
    closed_cfg.apply_sources = True
    open_cfg = MoversConfig(**cfg.as_dict())
    open_cfg.apply_sources = False

    closed = run_field_guided_movers(closed_cfg)
    open_loop = run_field_guided_movers(open_cfg)

    summarize("closed loop", closed)
    summarize("open loop", open_loop)

    tag = "open" if args.open_loop else "closed"
    out_path = os.path.join(args.figures_dir, f"06_field_guided_movers_{tag}.png")
    if args.open_loop:
        out_path = os.path.join(args.figures_dir, "06_field_guided_movers_open.png")
        plot(closed, open_loop, out_path)
    else:
        plot(closed, open_loop, out_path)


if __name__ == "__main__":
    main()