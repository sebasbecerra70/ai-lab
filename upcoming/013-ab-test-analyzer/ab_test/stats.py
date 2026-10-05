"""Statistics from scratch: normal and chi-square distributions, z-tests, intervals and power."""
from __future__ import annotations

import math
from dataclasses import dataclass


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation, |error| < 1.2e-9)."""
    if not 0 < p < 1:
        raise ValueError("p must be in (0, 1)")
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    lo = 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - lo:
        return -norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def chi2_sf(x: float, df: int) -> float:
    """P(X > x) for a chi-square with df degrees of freedom, via the regularized lower incomplete gamma."""
    if x <= 0:
        return 1.0
    s, z = df / 2, x / 2
    if z > s + 40:  # far tail: the series converges slowly and the answer is ~0 anyway
        return 0.0
    term = total = 1 / s
    k = 1
    while term > total * 1e-15:
        term *= z / (s + k)
        total += term
        k += 1
    lower = total * math.exp(-z + s * math.log(z) - math.lgamma(s))
    return max(0.0, 1 - lower)


@dataclass(frozen=True)
class ZTestResult:
    p_control: float
    p_treatment: float
    abs_lift: float
    rel_lift: float
    z: float
    p_value: float
    ci_low: float  # CI on the absolute difference
    ci_high: float


def two_proportion_ztest(conv_a: int, n_a: int, conv_b: int, n_b: int, alpha: float = 0.05) -> ZTestResult:
    """Two-sided test of H0: p_a == p_b. Pooled SE for the test, unpooled SE for the interval."""
    if min(n_a, n_b) <= 0:
        raise ValueError("both arms need visitors")
    pa, pb = conv_a / n_a, conv_b / n_b
    pooled = (conv_a + conv_b) / (n_a + n_b)
    se0 = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    z = (pb - pa) / se0 if se0 > 0 else 0.0
    p_value = 2 * (1 - norm_cdf(abs(z)))
    se1 = math.sqrt(pa * (1 - pa) / n_a + pb * (1 - pb) / n_b)
    zc = norm_ppf(1 - alpha / 2)
    diff = pb - pa
    return ZTestResult(pa, pb, diff, diff / pa if pa else float("nan"), z, p_value, diff - zc * se1, diff + zc * se1)


def sample_size_per_arm(baseline: float, mde_rel: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Visitors per arm to detect a relative lift of mde_rel over baseline (two-sided)."""
    p1, p2 = baseline, baseline * (1 + mde_rel)
    if not (0 < p1 < 1 and 0 < p2 < 1):
        raise ValueError("baseline and baseline*(1+mde) must be in (0, 1)")
    za, zb = norm_ppf(1 - alpha / 2), norm_ppf(power)
    pbar = (p1 + p2) / 2
    num = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return math.ceil(num / (p2 - p1) ** 2)


def achieved_power(baseline: float, mde_rel: float, n_per_arm: int, alpha: float = 0.05) -> float:
    """Power of a two-sided test with n_per_arm visitors to detect the given relative lift."""
    p1, p2 = baseline, baseline * (1 + mde_rel)
    se = math.sqrt(p1 * (1 - p1) / n_per_arm + p2 * (1 - p2) / n_per_arm)
    za = norm_ppf(1 - alpha / 2)
    shift = abs(p2 - p1) / se
    return norm_cdf(shift - za) + norm_cdf(-shift - za)


def srm_check(observed: list[int], expected_split: list[float]) -> tuple[float, float]:
    """Sample-ratio-mismatch chi-square test. Returns (statistic, p_value)."""
    total = sum(observed)
    if abs(sum(expected_split) - 1) > 1e-6:
        raise ValueError("expected_split must sum to 1")
    stat = sum((o - total * w) ** 2 / (total * w) for o, w in zip(observed, expected_split))
    return stat, chi2_sf(stat, len(observed) - 1)
