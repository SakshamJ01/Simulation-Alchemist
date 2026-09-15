"""Experiment D: Gated Mover Morphogenesis (Task 3.0, Build Stage 1).

The fourth repository composition -- {mesa, py-pde, pymunk/movers} -- where an
experiment-owned Mesa agent model senses the morphogen field *at each mover's
current position* and decides, with hysteresis (threshold + cooldown), whether
that mover's chemical source stays armed.  The science (gating rule, schedule,
coupling contracts) lives in this package; the generic core, the composition
catalog, and the cross-composition layers are untouched in Stage 1.
"""