from __future__ import annotations

from collections.abc import Hashable

import numpy as np


def _validate_q_1d(q: np.ndarray) -> np.ndarray:
    q_arr = np.asarray(q, dtype=float)
    if q_arr.ndim != 1:
        raise ValueError(f"q must be a 1-dimensional array, got ndim={q_arr.ndim}")
    if q_arr.size == 0:
        raise ValueError("q must contain at least one element")
    if not np.isfinite(q_arr).all():
        raise ValueError("q must contain only finite values")
    return q_arr


def _validate_scalar_params(
    *,
    q_size: int,
    k: float,
    eps: float,
    lower: float,
    upper: float,
    tol: float,
    max_iter: int,
) -> None:
    if not np.isfinite(k):
        raise ValueError("k must be finite")
    if k < 0.0 or k > float(q_size):
        raise ValueError(f"k must satisfy 0 <= k <= len(q), got k={k}, len(q)={q_size}")
    if not np.isfinite(eps) or eps <= 0.0 or eps >= 0.5:
        raise ValueError(f"eps must satisfy 0 < eps < 0.5, got eps={eps}")
    if not np.isfinite(lower) or not np.isfinite(upper) or lower >= upper:
        raise ValueError(f"lower/upper must be finite with lower < upper, got lower={lower}, upper={upper}")
    if not np.isfinite(tol) or tol <= 0.0:
        raise ValueError(f"tol must be positive and finite, got tol={tol}")
    if max_iter <= 0:
        raise ValueError(f"max_iter must be positive, got max_iter={max_iter}")


def _logit(p: np.ndarray) -> np.ndarray:
    return np.log(p / (1.0 - p))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    out = np.empty_like(x_arr, dtype=float)
    pos = x_arr >= 0.0
    out[pos] = 1.0 / (1.0 + np.exp(-x_arr[pos]))
    exp_x = np.exp(x_arr[~pos])
    out[~pos] = exp_x / (1.0 + exp_x)
    return out


def _shifted_sum(logits: np.ndarray, shift: float) -> float:
    return float(_sigmoid(logits + shift).sum())


def _expand_bracketing_bounds(
    *,
    logits: np.ndarray,
    target: float,
    lower: float,
    upper: float,
    tol: float,
    max_expand: int = 32,
) -> tuple[float, float, float, float]:
    left = float(lower)
    right = float(upper)
    low_val = _shifted_sum(logits, left) - target
    high_val = _shifted_sum(logits, right) - target

    step = max(abs(right - left), 1.0)
    for _ in range(max_expand):
        if low_val <= 0.0 or abs(low_val) <= tol:
            break
        left -= step
        step *= 2.0
        low_val = _shifted_sum(logits, left) - target
    else:
        raise ValueError("lower bound is too large to bracket the requested k")

    step = max(abs(right - left), 1.0)
    for _ in range(max_expand):
        if high_val >= 0.0 or abs(high_val) <= tol:
            break
        right += step
        step *= 2.0
        high_val = _shifted_sum(logits, right) - target
    else:
        raise ValueError("upper bound is too small to bracket the requested k")

    return left, right, low_val, high_val


def solve_logit_shift_lambda(
    q: np.ndarray,
    k: float,
    *,
    eps: float = 1e-12,
    lower: float = -20.0,
    upper: float = 20.0,
    tol: float = 1e-10,
    max_iter: int = 200,
) -> float:
    q_arr = _validate_q_1d(q)
    _validate_scalar_params(
        q_size=q_arr.size,
        k=float(k),
        eps=eps,
        lower=lower,
        upper=upper,
        tol=tol,
        max_iter=max_iter,
    )

    q_clipped = np.clip(q_arr, eps, 1.0 - eps)
    logits = _logit(q_clipped)
    target = float(k)
    if target == 0.0:
        return float(lower)
    if target == float(q_arr.size):
        return float(upper)

    left, right, low_val, high_val = _expand_bracketing_bounds(
        logits=logits,
        target=target,
        lower=lower,
        upper=upper,
        tol=tol,
    )
    if abs(low_val) <= tol:
        return float(left)
    if abs(high_val) <= tol:
        return float(right)

    for _ in range(max_iter):
        mid = (left + right) / 2.0
        mid_val = _shifted_sum(logits, mid) - target
        if abs(mid_val) <= tol or (right - left) / 2.0 <= tol:
            return float(mid)
        if mid_val < 0.0:
            left = mid
        else:
            right = mid

    return float((left + right) / 2.0)


def apply_logit_shift(
    q: np.ndarray,
    k: float,
    *,
    eps: float = 1e-12,
    lower: float = -20.0,
    upper: float = 20.0,
    tol: float = 1e-10,
    max_iter: int = 200,
    return_lambda: bool = False,
) -> np.ndarray | tuple[np.ndarray, float]:
    q_arr = _validate_q_1d(q)
    shift = solve_logit_shift_lambda(
        q_arr,
        k,
        eps=eps,
        lower=lower,
        upper=upper,
        tol=tol,
        max_iter=max_iter,
    )
    q_clipped = np.clip(q_arr, eps, 1.0 - eps)
    shifted = _sigmoid(_logit(q_clipped) + shift).astype(float)
    if return_lambda:
        return shifted, shift
    return shifted


def apply_logit_shift_grouped(
    q: np.ndarray,
    group_ids: np.ndarray,
    k_by_group: dict[str, float] | dict[int, float],
    *,
    eps: float = 1e-12,
    lower: float = -20.0,
    upper: float = 20.0,
    tol: float = 1e-10,
    max_iter: int = 200,
    return_lambda: bool = False,
) -> np.ndarray | tuple[np.ndarray, dict[object, float]]:
    q_arr = _validate_q_1d(q)
    group_arr = np.asarray(group_ids)
    if group_arr.ndim != 1:
        raise ValueError(f"group_ids must be a 1-dimensional array, got ndim={group_arr.ndim}")
    if group_arr.size != q_arr.size:
        raise ValueError(
            f"group_ids must have the same length as q, got len(group_ids)={group_arr.size}, len(q)={q_arr.size}"
        )
    if k_by_group is None:
        raise ValueError("k_by_group must not be None")

    out = np.empty_like(q_arr, dtype=float)
    lambdas: dict[object, float] = {}

    masks_by_group: dict[object, np.ndarray] = {}
    for index, group_value in enumerate(group_arr):
        group_key = group_value.item() if hasattr(group_value, "item") else group_value
        if not isinstance(group_key, Hashable):
            raise ValueError(f"group_id must be hashable, got {type(group_key)!r}")
        if group_key not in masks_by_group:
            masks_by_group[group_key] = np.zeros(q_arr.size, dtype=bool)
        masks_by_group[group_key][index] = True

    for group_key, mask in masks_by_group.items():
        if group_key not in k_by_group:
            raise KeyError(f"missing k for group_id={group_key!r}")
        group_q = q_arr[mask]
        group_k = float(k_by_group[group_key])
        shifted, shift = apply_logit_shift(
            group_q,
            group_k,
            eps=eps,
            lower=lower,
            upper=upper,
            tol=tol,
            max_iter=max_iter,
            return_lambda=True,
        )
        out[mask] = shifted
        lambdas[group_key] = shift

    if return_lambda:
        return out, lambdas
    return out
