from __future__ import annotations

import numpy as np


def wrap_angle(angle_rad: float) -> float:
    return float((angle_rad + np.pi) % (2.0 * np.pi) - np.pi)


def symmetrize(a: np.ndarray) -> np.ndarray:
    return 0.5 * (a + a.T)


def nearest_psd(a: np.ndarray, eigen_floor: float) -> np.ndarray:
    a = symmetrize(np.asarray(a, dtype=float))
    vals, vecs = np.linalg.eigh(a)
    vals = np.maximum(vals, eigen_floor)
    return symmetrize((vecs * vals) @ vecs.T)


def require_finite(name: str, value: np.ndarray | float) -> None:
    arr = np.asarray(value, dtype=float)
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains non-finite values")
