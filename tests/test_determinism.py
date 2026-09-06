"""Determinism / replay validation test (Task 0.3 check G).

Two runs with an identical seed must be bitwise identical end to end: final
field, wall centre-of-mass tracks, mean forces, mean speeds, and every agent
decision log.  Same-runtime/environment determinism only - this is NOT a claim
of cross-platform bitwise equivalence.
"""


def test_replay_final_field_bitwise(experiments) -> None:
    assert (experiments["dynamic"].final_u
            == experiments["replay"].final_u).all()


def test_replay_wall_tracks_identical(experiments) -> None:
    assert experiments["dynamic"].wall_tracks == experiments["replay"].wall_tracks


def test_replay_force_series_identical(experiments) -> None:
    assert experiments["dynamic"].force_mags == experiments["replay"].force_mags


def test_replay_speed_series_identical(experiments) -> None:
    assert experiments["dynamic"].wall_speeds == experiments["replay"].wall_speeds


def test_replay_agent_decisions_identical(experiments) -> None:
    dyn, replay = experiments["dynamic"], experiments["replay"]
    for i in range(len(dyn.agent_histories)):
        for h, hr in zip(dyn.decisions(i), replay.decisions(i)):
            assert (h["built"], h["dissolved"], round(h["gmag"], 12)) == (
                hr["built"], hr["dissolved"], round(hr["gmag"], 12)
            )