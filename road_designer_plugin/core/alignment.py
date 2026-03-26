from __future__ import annotations

import math
from typing import List, Tuple

from qgis.core import QgsGeometry, QgsPointXY, QgsVectorLayer

from ..utils.geometry_utils import normalize

Point2D = Tuple[float, float]


class Alignment:
    def __init__(self, points: List[Point2D], progressive: List[float]):
        self.points = points
        self.progressive = progressive
        self.length = progressive[-1] if progressive else 0.0

    def point_and_tangent_at(self, s: float) -> Tuple[Point2D, Point2D]:
        if not self.points:
            return (0.0, 0.0), (1.0, 0.0)
        if s <= 0:
            p0, p1 = self.points[0], self.points[min(1, len(self.points) - 1)]
            return p0, normalize(p1[0] - p0[0], p1[1] - p0[1])
        if s >= self.length:
            p0, p1 = self.points[-2], self.points[-1]
            return p1, normalize(p1[0] - p0[0], p1[1] - p0[1])
        for i in range(1, len(self.progressive)):
            if self.progressive[i] >= s:
                s0, s1 = self.progressive[i - 1], self.progressive[i]
                t = 0.0 if s1 == s0 else (s - s0) / (s1 - s0)
                p0, p1 = self.points[i - 1], self.points[i]
                x = p0[0] + (p1[0] - p0[0]) * t
                y = p0[1] + (p1[1] - p0[1]) * t
                return (x, y), normalize(p1[0] - p0[0], p1[1] - p0[1])
        return self.points[-1], (1.0, 0.0)


class AlignmentBuilder:
    def build(self, axis_layer: QgsVectorLayer, min_radius: float, sample_step: float) -> Alignment:
        points = self._extract_axis_points(axis_layer)
        smoothed = self._smooth_polyline_with_arcs(points, min_radius)
        sampled = self._resample(smoothed, sample_step)
        progressive = [0.0]
        for i in range(1, len(sampled)):
            progressive.append(progressive[-1] + math.dist(sampled[i - 1], sampled[i]))
        return Alignment(sampled, progressive)

    def _extract_axis_points(self, layer: QgsVectorLayer) -> List[Point2D]:
        selected = list(layer.selectedFeatureIds())
        if len(selected) == 1:
            feat = next(layer.getFeatures(selected), None)
        else:
            feature_count = layer.featureCount()
            if feature_count != 1:
                raise ValueError(
                    "Il layer asse deve contenere una sola feature "
                    "(oppure selezionarne esattamente una)."
                )
            feat = next(layer.getFeatures(), None)
        if not feat:
            return []
        geom: QgsGeometry = feat.geometry()
        if geom.isEmpty():
            return []
        if geom.isMultipart():
            parts = geom.asMultiPolyline()
            if not parts:
                return []
            line = max(parts, key=len)
        else:
            line = geom.asPolyline()
        return [(p.x(), p.y()) for p in line]

    def _smooth_polyline_with_arcs(self, points: List[Point2D], min_radius: float) -> List[Point2D]:
        if len(points) < 3:
            return points
        out = [points[0]]
        for i in range(1, len(points) - 1):
            p_prev, p, p_next = points[i - 1], points[i], points[i + 1]
            seg_in = math.dist(p_prev, p)
            seg_out = math.dist(p, p_next)
            if seg_in <= 1e-6 or seg_out <= 1e-6:
                out.append(p)
                continue

            v_in = normalize(p[0] - p_prev[0], p[1] - p_prev[1])
            v_out = normalize(p_next[0] - p[0], p_next[1] - p[1])
            dot = max(-1.0, min(1.0, v_in[0] * v_out[0] + v_in[1] * v_out[1]))
            deflection = math.acos(dot)

            if deflection < math.radians(2.0) or deflection > math.radians(175.0):
                out.append(p)
                continue

            half = deflection / 2.0
            tan_half = math.tan(half)
            if abs(tan_half) < 1e-9:
                out.append(p)
                continue

            trim = min(max(min_radius, 1e-3) * tan_half, seg_in * 0.45, seg_out * 0.45)
            if trim <= 1e-4:
                out.append(p)
                continue

            radius = trim / tan_half
            p_in = (p[0] - v_in[0] * trim, p[1] - v_in[1] * trim)
            p_out = (p[0] + v_out[0] * trim, p[1] + v_out[1] * trim)

            turn = v_in[0] * v_out[1] - v_in[1] * v_out[0]
            if abs(turn) < 1e-9:
                out.append(p)
                continue
            left_turn = turn > 0
            n_in = (-v_in[1], v_in[0]) if left_turn else (v_in[1], -v_in[0])
            center = (p_in[0] + n_in[0] * radius, p_in[1] + n_in[1] * radius)

            a0 = math.atan2(p_in[1] - center[1], p_in[0] - center[0])
            a1 = math.atan2(p_out[1] - center[1], p_out[0] - center[0])
            if left_turn and a1 < a0:
                a1 += 2 * math.pi
            if (not left_turn) and a1 > a0:
                a1 -= 2 * math.pi

            arc_len = abs(a1 - a0) * radius
            segments = max(4, int(arc_len / 3.0))
            out.append(p_in)
            for j in range(1, segments):
                tt = j / segments
                aa = a0 + (a1 - a0) * tt
                out.append((center[0] + radius * math.cos(aa), center[1] + radius * math.sin(aa)))
            out.append(p_out)
        out.append(points[-1])
        return out

    def _resample(self, points: List[Point2D], step: float) -> List[Point2D]:
        if len(points) < 2 or step <= 0:
            return points
        out = [points[0]]
        carry = 0.0
        for i in range(1, len(points)):
            p0, p1 = points[i - 1], points[i]
            seg_len = math.dist(p0, p1)
            if seg_len == 0:
                continue
            ux, uy = (p1[0] - p0[0]) / seg_len, (p1[1] - p0[1]) / seg_len
            cur = step - carry
            while cur < seg_len:
                out.append((p0[0] + ux * cur, p0[1] + uy * cur))
                cur += step
            carry = seg_len - (cur - step)
        if out[-1] != points[-1]:
            out.append(points[-1])
        return out
