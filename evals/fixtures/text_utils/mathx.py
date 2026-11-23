"""Small numeric helpers."""


def clamp(x: float, lo: float, hi: float) -> float:
    """Limit `x` to the inclusive range [lo, hi]."""
    return max(lo, min(x, hi))


def mean(values: list[float]) -> float:
    """Arithmetic mean of `values`. Raises ValueError for an empty list."""
    if not values:
        raise ValueError("mean() of empty list")
    return sum(values) / len(values)
