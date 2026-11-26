"""Small-sample statistics for eval reports."""


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% CI for a proportion; honest error bars for small eval sets."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (round(centre - half, 3), round(centre + half, 3))
