def quantile(values, probability):
    """Linear interpolation at (n - 1) * probability (R type 7)."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    index = (len(values) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def distribution(values):
    values = [v for v in values if v is not None]
    return {"n": len(values), "median": quantile(values, .5),
            "p95": quantile(values, .95), "p99": quantile(values, .99)}
