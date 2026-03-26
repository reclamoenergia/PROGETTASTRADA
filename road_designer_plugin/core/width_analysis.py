from __future__ import annotations

import math
from typing import List, Tuple

from qgis.core import QgsGeometry, QgsPointXY, QgsVectorLayer, QgsWkbTypes

from .models import WidthInfo


class WidthAnalysis:
    def __init__(self, polygon_layer: QgsVectorLayer, min_platform_width: float):
        self.polygon_layer = polygon_layer
        self.min_half = min_platform_width / 2.0
        self.union_geom = self._build_union()

    def _build_union(self) -> QgsGeometry:
        geoms = [f.geometry() for f in self.polygon_layer.getFeatures()]
        if not geoms:
            return QgsGeometry()
        out = geoms[0]
        for g in geoms[1:]:
            out = out.combine(g)
        return out

    def analyze(self, section_line: QgsGeometry, axis_point: Tuple[float, float]) -> WidthInfo:
        if self.union_geom.isEmpty():
            return WidthInfo(self.min_half, self.min_half, self.min_half * 2, "STANDARD")
        inter = self.union_geom.intersection(section_line)
        if inter.isEmpty():
            return WidthInfo(self.min_half, self.min_half, self.min_half * 2, "STANDARD")
        section_pts = section_line.asPolyline()
        if len(section_pts) < 2:
            return WidthInfo(self.min_half, self.min_half, self.min_half * 2, "STANDARD")
        p0, p1 = section_pts[0], section_pts[-1]
        vx, vy = p1.x() - p0.x(), p1.y() - p0.y()
        norm = max(1e-9, (vx * vx + vy * vy) ** 0.5)
        ux, uy = vx / norm, vy / norm
        axis = QgsPointXY(axis_point[0], axis_point[1])

        intervals = self._extract_intervals(inter, p0, ux, uy)
        if not intervals:
            return WidthInfo(self.min_half, self.min_half, self.min_half * 2, "STANDARD")
        axis_t = (axis.x() - p0.x()) * ux + (axis.y() - p0.y()) * uy
        containing = [iv for iv in intervals if iv[0] - 1e-6 <= axis_t <= iv[1] + 1e-6]
        if containing:
            t0, t1 = max(containing, key=lambda iv: iv[1] - iv[0])
        else:
            t0, t1 = min(intervals, key=lambda iv: min(abs(iv[0] - axis_t), abs(iv[1] - axis_t)))
        left = max(self.min_half, max(0.0, axis_t - t0))
        right = max(self.min_half, max(0.0, t1 - axis_t))
        label = "STANDARD"
        if left > self.min_half * 1.8 and right > self.min_half * 1.8:
            label = "PAD_BOTH"
        elif left > self.min_half * 2.5:
            label = "PAD_LEFT"
        elif right > self.min_half * 2.5:
            label = "PAD_RIGHT"
        elif left > self.min_half * 1.3:
            label = "WIDENING_LEFT"
        elif right > self.min_half * 1.3:
            label = "WIDENING_RIGHT"
        return WidthInfo(left, right, left + right, label)

    def _extract_intervals(self, geom: QgsGeometry, ref: QgsPointXY, ux: float, uy: float) -> List[Tuple[float, float]]:
        intervals: List[Tuple[float, float]] = []
        gtype = QgsWkbTypes.geometryType(geom.wkbType())
        if gtype == QgsWkbTypes.LineGeometry:
            parts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
            for part in parts:
                if len(part) < 2:
                    continue
                scalars = [((p.x() - ref.x()) * ux + (p.y() - ref.y()) * uy) for p in part]
                intervals.append((min(scalars), max(scalars)))
        elif gtype == QgsWkbTypes.PointGeometry:
            pts = self._extract_points(geom)
            if len(pts) >= 2:
                scalars = [((p.x() - ref.x()) * ux + (p.y() - ref.y()) * uy) for p in pts]
                scalars.sort()
                for i in range(0, len(scalars) - 1, 2):
                    intervals.append((scalars[i], scalars[i + 1]))
        elif gtype == QgsWkbTypes.PolygonGeometry:
            # fallback robusto per geometrie patologiche: usa bbox della parte intersecata
            bb = geom.boundingBox()
            c0 = (bb.xMinimum() - ref.x()) * ux + (bb.yMinimum() - ref.y()) * uy
            c1 = (bb.xMaximum() - ref.x()) * ux + (bb.yMaximum() - ref.y()) * uy
            intervals.append((min(c0, c1), max(c0, c1)))
        merged: List[Tuple[float, float]] = []
        for a, b in sorted(intervals):
            if not merged or a > merged[-1][1] + 1e-6:
                merged.append((a, b))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        return [(a, b) for a, b in merged if math.isfinite(a) and math.isfinite(b) and b - a > 1e-6]

    def _extract_points(self, geom: QgsGeometry):
        gtype = QgsWkbTypes.geometryType(geom.wkbType())
        pts = []
        if gtype == QgsWkbTypes.PointGeometry:
            if geom.isMultipart():
                pts = [QgsPointXY(p.x(), p.y()) for p in geom.asMultiPoint()]
            else:
                p = geom.asPoint()
                pts = [QgsPointXY(p.x(), p.y())]
        elif gtype == QgsWkbTypes.LineGeometry:
            if geom.isMultipart():
                for part in geom.asMultiPolyline():
                    pts.extend([QgsPointXY(p.x(), p.y()) for p in part])
            else:
                pts = [QgsPointXY(p.x(), p.y()) for p in geom.asPolyline()]
        return pts
