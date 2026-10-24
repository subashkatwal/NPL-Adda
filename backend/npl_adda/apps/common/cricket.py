"""
Deterministic cricket calculations. Overs are always derived from integer legal balls
and rates use Decimal, so results never depend on floating-point rounding.
"""
from decimal import ROUND_HALF_UP, Decimal

BALLS_PER_OVER = 6
TWO_PLACES = Decimal("0.01")


def overs(legal_balls):
    """120 -> "20.0", 112 -> "18.4"."""
    return f"{legal_balls // BALLS_PER_OVER}.{legal_balls % BALLS_PER_OVER}"


def _rate(numerator, denominator):
    if not denominator:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def run_rate(runs, legal_balls):
    return _rate(runs * BALLS_PER_OVER, legal_balls)


def required_run_rate(target, runs, legal_balls, balls_per_innings):
    remaining = balls_per_innings - legal_balls
    needed = target - runs
    if needed <= 0:
        return Decimal("0.00")
    return _rate(needed * BALLS_PER_OVER, remaining)


def strike_rate(runs, balls_faced):
    return _rate(runs * 100, balls_faced)


def economy(runs_conceded, bowling_balls):
    return _rate(runs_conceded * BALLS_PER_OVER, bowling_balls)
