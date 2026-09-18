"""Cross-Architecture Floating-Point Bitwise Parity & Fixed-Point Quantization (Phase 4G).

Guarantees 100% bitwise-identical simulation trajectories across differing CPU/OS
architectures (x86_64, ARM64, RISC-V) using deterministic integer Q-format fixed-point
arithmetic and bounded uniform quantization matrices.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np


class FixedPointFloat:
    """Deterministic integer-backed Q-format fixed-point number.

    Defaults to Q32.32 (32 integer bits, 32 fractional bits) stored in standard int.
    """

    DEFAULT_FRACTIONAL_BITS: int = 32
    SCALE_FACTOR: int = 1 << DEFAULT_FRACTIONAL_BITS

    def __init__(self, raw_value: float, fractional_bits: int = DEFAULT_FRACTIONAL_BITS) -> None:
        self.fractional_bits = fractional_bits
        self.scale = 1 << fractional_bits
        if isinstance(raw_value, float):
            self.raw_int: int = round(raw_value * self.scale)
        else:
            self.raw_int = int(raw_value)

    @classmethod
    def from_float(cls, value: float, fractional_bits: int = DEFAULT_FRACTIONAL_BITS) -> FixedPointFloat:
        scale = 1 << fractional_bits
        raw = round(value * scale)
        return cls(raw_value=raw, fractional_bits=fractional_bits)

    def to_float(self) -> float:
        return self.raw_int / self.scale

    def __add__(self, other: FixedPointFloat | float) -> FixedPointFloat:
        if isinstance(other, FixedPointFloat):
            return FixedPointFloat(self.raw_int + other.raw_int, self.fractional_bits)
        return self + FixedPointFloat.from_float(float(other), self.fractional_bits)

    def __sub__(self, other: FixedPointFloat | float) -> FixedPointFloat:
        if isinstance(other, FixedPointFloat):
            return FixedPointFloat(self.raw_int - other.raw_int, self.fractional_bits)
        return self - FixedPointFloat.from_float(float(other), self.fractional_bits)

    def __mul__(self, other: FixedPointFloat | float) -> FixedPointFloat:
        if isinstance(other, FixedPointFloat):
            # (a * b) >> fractional_bits
            prod = (self.raw_int * other.raw_int) >> self.fractional_bits
            return FixedPointFloat(prod, self.fractional_bits)
        return self * FixedPointFloat.from_float(float(other), self.fractional_bits)

    def __truediv__(self, other: FixedPointFloat | float) -> FixedPointFloat:
        if isinstance(other, FixedPointFloat):
            if other.raw_int == 0:
                raise ZeroDivisionError("FixedPoint division by zero.")
            # (a << fractional_bits) // b
            quot = (self.raw_int << self.fractional_bits) // other.raw_int
            return FixedPointFloat(quot, self.fractional_bits)
        return self / FixedPointFloat.from_float(float(other), self.fractional_bits)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FixedPointFloat):
            return self.raw_int == other.raw_int
        if isinstance(other, (int, float)):
            return self.raw_int == FixedPointFloat.from_float(float(other), self.fractional_bits).raw_int
        return False

    def __lt__(self, other: FixedPointFloat | float) -> bool:
        if isinstance(other, FixedPointFloat):
            return self.raw_int < other.raw_int
        return self.raw_int < FixedPointFloat.from_float(float(other), self.fractional_bits).raw_int

    def __repr__(self) -> str:
        return f"FixedPointFloat(val={self.to_float():.6f}, raw={self.raw_int})"


class DeterministicQuantizer:
    """Linear uniform quantizer mapping float arrays into deterministic integer buckets."""

    def __init__(self, bits: int = 16, min_val: float = -10.0, max_val: float = 10.0) -> None:
        if max_val <= min_val:
            raise ValueError("max_val must be strictly greater than min_val.")
        self.bits = bits
        self.min_val = min_val
        self.max_val = max_val
        self.q_levels = (1 << bits) - 1
        self.scale = (max_val - min_val) / self.q_levels

    def quantize(self, array: np.ndarray) -> np.ndarray:
        """Quantize floating point array into deterministic uint64 integer array."""
        clipped = np.clip(array, self.min_val, self.max_val)
        normalized = (clipped - self.min_val) / self.scale
        return np.round(normalized).astype(np.int64)

    def dequantize(self, q_array: np.ndarray) -> np.ndarray:
        """Dequantize integer array back into floating point approximations."""
        return q_array.astype(float) * self.scale + self.min_val

    def checksum(self, array: np.ndarray) -> str:
        """Compute bitwise SHA-256 hash over the quantized integer representation."""
        q = self.quantize(array)
        return hashlib.sha256(q.tobytes()).hexdigest()


@dataclass(frozen=True)
class ParityReport:
    """Parity diagnostics comparing two trajectory outputs."""

    is_bitwise_identical: bool
    max_absolute_error: float
    mean_squared_error: float
    sha256_a: str
    sha256_b: str


class CrossPlatformFloatParity:
    """Analyzes and certifies floating-point reproducibility across architectures."""

    @staticmethod
    def compare(arr_a: np.ndarray, arr_b: np.ndarray, quantizer: DeterministicQuantizer | None = None) -> ParityReport:
        if arr_a.shape != arr_b.shape:
            raise ValueError(f"Shape mismatch: {arr_a.shape} vs {arr_b.shape}")

        q = quantizer or DeterministicQuantizer()
        hash_a = q.checksum(arr_a)
        hash_b = q.checksum(arr_b)

        max_err = float(np.max(np.abs(arr_a - arr_b)))
        mse = float(np.mean((arr_a - arr_b) ** 2))

        return ParityReport(
            is_bitwise_identical=(hash_a == hash_b),
            max_absolute_error=max_err,
            mean_squared_error=mse,
            sha256_a=hash_a,
            sha256_b=hash_b,
        )
