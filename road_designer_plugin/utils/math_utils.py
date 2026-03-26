from __future__ import annotations

import math
from typing import Iterable, List, Tuple


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def trapezoid_area(x: List[float], y: List[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    area = 0.0
    for i in range(1, len(x)):
        area += (x[i] - x[i - 1]) * (y[i] + y[i - 1]) / 2.0
    return area


def diff_signed_segments(x: List[float], d: List[float]) -> Tuple[float, float]:
    cut = 0.0
    fill = 0.0
    for i in range(1, len(x)):
        dx = x[i] - x[i - 1]
        d0, d1 = d[i - 1], d[i]
        if d0 >= 0 and d1 >= 0:
            fill += dx * (d0 + d1) / 2.0
        elif d0 <= 0 and d1 <= 0:
            cut += abs(dx * (d0 + d1) / 2.0)
        else:
            t = abs(d0) / (abs(d0) + abs(d1))
            xm = dx * t
            if d0 > 0:
                fill += xm * d0 / 2.0
                cut += abs((dx - xm) * d1 / 2.0)
            else:
                cut += abs(xm * d0 / 2.0)
                fill += (dx - xm) * d1 / 2.0
    return cut, fill


def cumulative_distance(points: Iterable[Tuple[float, float]]) -> List[float]:
    out = [0.0]
    prev = None
    for pt in points:
        if prev is not None:
            out.append(out[-1] + math.dist(prev, pt))
        prev = pt
    return out
