"""Tests for Fixed-Point Quantization and Cross-Architecture Bitwise Parity (Phase 4G)."""

from __future__ import annotations

import numpy as np

from sim_alchemist.core.quantization import (
    CrossPlatformFloatParity,
    DeterministicQuantizer,
    FixedPointFloat,
)


def test_fixed_point_arithmetic() -> None:
    a = FixedPointFloat.from_float(3.5)
    b = FixedPointFloat.from_float(2.0)

    # Addition
    c = a + b
    assert abs(c.to_float() - 5.5) < 1e-6

    # Subtraction
    d = a - b
    assert abs(d.to_float() - 1.5) < 1e-6

    # Multiplication
    e = a * b
    assert abs(e.to_float() - 7.0) < 1e-6

    # Division
    f = a / b
    assert abs(f.to_float() - 1.75) < 1e-6


def test_deterministic_quantizer_roundtrip_and_checksum() -> None:
    quantizer = DeterministicQuantizer(bits=16, min_val=-5.0, max_val=5.0)
    arr = np.array([-5.0, -2.5, 0.0, 2.5, 5.0])

    q = quantizer.quantize(arr)
    assert q[0] == 0
    assert q[-1] == (1 << 16) - 1

    deq = quantizer.dequantize(q)
    assert np.allclose(arr, deq, atol=1e-3)

    chk1 = quantizer.checksum(arr)
    chk2 = quantizer.checksum(arr.copy())
    assert chk1 == chk2


def test_cross_platform_parity() -> None:
    arr_a = np.array([1.2345, 6.7890, -3.1415])
    arr_b = np.array([1.2345, 6.7890, -3.1415])
    arr_c = np.array([1.2345, 6.7890, -3.1400])

    rep1 = CrossPlatformFloatParity.compare(arr_a, arr_b)
    assert rep1.is_bitwise_identical
    assert rep1.max_absolute_error == 0.0

    rep2 = CrossPlatformFloatParity.compare(arr_a, arr_c)
    assert not rep2.is_bitwise_identical
    assert rep2.max_absolute_error > 0.0
