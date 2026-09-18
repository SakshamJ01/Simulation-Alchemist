"""Unit tests for first-class reusable coupling primitives (Phase 4D)."""

import pytest

from sim_alchemist.core.couplings import (
    CouplingPipeline,
    CouplingTransformer,
    HysteresisFilter,
    SaturationFilter,
    SigmoidTransfer,
    TemporalDelayBuffer,
)


def test_hysteresis_filter_switching_and_cooldown():
    filt = HysteresisFilter(low_threshold=2.0, high_threshold=8.0, cooldown_steps=2)
    assert isinstance(filt, CouplingTransformer)
    assert not filt.is_active

    # Below high threshold -> stays inactive
    assert filt.transform(5.0) == 0.0
    assert not filt.is_active

    # Exceeds high threshold -> switches to active
    assert filt.transform(8.5) == 1.0
    assert filt.is_active

    # Drops below low threshold, but in cooldown -> stays active
    assert filt.transform(1.0) == 1.0  # cooldown step 1
    assert filt.transform(1.0) == 1.0  # cooldown step 2

    # Now cooldown elapsed, drops below low threshold -> switches to inactive
    assert filt.transform(1.0) == 0.0
    assert not filt.is_active

    # Checkpoint state restoration
    state = filt.state_dict()
    filt.reset()
    assert not filt.is_active
    filt.load_state_dict(state)


def test_hysteresis_validation():
    with pytest.raises(ValueError, match="must be <="):
        HysteresisFilter(low_threshold=10.0, high_threshold=5.0)
    with pytest.raises(ValueError, match="cannot be negative"):
        HysteresisFilter(low_threshold=1.0, high_threshold=2.0, cooldown_steps=-1)


def test_temporal_delay_buffer():
    buf = TemporalDelayBuffer(delay_steps=3, default_value=-1.0)
    assert isinstance(buf, CouplingTransformer)

    inputs = [10.0, 20.0, 30.0, 40.0, 50.0]
    expected_outputs = [-1.0, -1.0, -1.0, 10.0, 20.0]

    outputs = [buf.transform(x) for x in inputs]
    assert outputs == expected_outputs

    # State serialization
    state = buf.state_dict()
    buf.reset()
    assert buf.transform(99.0) == -1.0
    buf.load_state_dict(state)
    assert buf.transform(60.0) == 30.0


def test_sigmoid_and_saturation():
    sig = SigmoidTransfer(midpoint=0.0, steepness=2.0, lower_bound=-1.0, upper_bound=1.0)
    assert isinstance(sig, CouplingTransformer)

    # At midpoint, value is (lower + upper) / 2 = 0.0
    assert pytest.approx(sig.transform(0.0), abs=1e-6) == 0.0
    # High input -> upper bound
    assert pytest.approx(sig.transform(10.0), abs=1e-3) == 1.0
    # Low input -> lower bound
    assert pytest.approx(sig.transform(-10.0), abs=1e-3) == -1.0

    sat = SaturationFilter(min_val=0.0, max_val=10.0, scale=2.0, bias=1.0)
    assert sat.transform(3.0) == 7.0  # 3*2 + 1 = 7
    assert sat.transform(10.0) == 10.0  # 10*2 + 1 = 21 -> clamped to 10
    assert sat.transform(-5.0) == 0.0  # -5*2 + 1 = -9 -> clamped to 0


def test_coupling_pipeline_chaining():
    sig = SigmoidTransfer(midpoint=0.0, steepness=1.0, lower_bound=0.0, upper_bound=10.0)
    sat = SaturationFilter(min_val=2.0, max_val=8.0)
    pipeline = CouplingPipeline(transformers=[sig, sat])

    # Transform through pipeline
    out_mid = pipeline.transform(0.0)  # sigmoid gives 5.0 -> saturation gives 5.0
    assert pytest.approx(out_mid, abs=1e-5) == 5.0

    out_high = pipeline.transform(100.0)  # sigmoid gives ~10.0 -> saturation clamps to 8.0
    assert pytest.approx(out_high, abs=1e-5) == 8.0

    out_low = pipeline.transform(-100.0)  # sigmoid gives ~0.0 -> saturation clamps to 2.0
    assert pytest.approx(out_low, abs=1e-5) == 2.0
