from __future__ import annotations

import math
from typing import List, Optional, Tuple

from qgis.core import QgsGeometry, QgsPointXY


Point2D = Tuple[float, float]


def normalize(vx: float, vy: float) -> Point2D:
    n = math.hypot(vx, vy)
    if n == 0:
        return (1.0, 0.0)
    return (vx / n, vy / n)


def perpendicular(vx: float, vy: float) -> Point2D:
    return (-vy, vx)


def point_offset(point: Point2D, direction: Point2D, distance: float) -> Point2D:
    return (point[0] + direction[0] * distance, point[1] + direction[1] * distance)


def line_from_point_dir(point: Point2D, direction: Point2D, half_len: float) -> QgsGeometry:
    p1 = QgsPointXY(point[0] - direction[0] * half_len, point[1] - direction[1] * half_len)
    p2 = QgsPointXY(point[0] + direction[0] * half_len, point[1] + direction[1] * half_len)
    return QgsGeometry.fromPolylineXY([p1, p2])


def as_xy(qpt: QgsPointXY) -> Point2D:
    return (qpt.x(), qpt.y())


def circle_points(
    center: Point2D,
    radius: float,
    a0: float,
    a1: float,
    segments: int,
) -> List[Point2D]:
    if segments < 2:
        segments = 2
    pts: List[Point2D] = []
    for i in range(segments + 1):
        t = i / segments
        a = a0 + (a1 - a0) * t
        pts.append((center[0] + radius * math.cos(a), center[1] + radius * math.sin(a)))
    return pts


def nearest_point_index(points: List[Point2D], target: Point2D) -> Optional[int]:
    if not points:
        return None
    best = 0
    best_d = float("inf")
    for i, p in enumerate(points):
        d = math.dist(p, target)
        if d < best_d:
            best_d = d
            best = i
    return best
