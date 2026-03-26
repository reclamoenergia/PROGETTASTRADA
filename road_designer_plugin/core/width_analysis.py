from __future__ import annotations

from typing import Tuple

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
        axis = QgsPointXY(axis_point[0], axis_point[1])
        pts = self._extract_points(inter)
        if len(pts) < 2:
            return WidthInfo(self.min_half, self.min_half, self.min_half * 2, "STANDARD")
        signed = []
        # usa orientazione della sezione (primo->ultimo punto)
        p0, p1 = pts[0], pts[-1]
        vx, vy = p1.x() - p0.x(), p1.y() - p0.y()
        for p in pts:
            ax, ay = p.x() - axis.x(), p.y() - axis.y()
            sign = 1.0 if (vx * ay - vy * ax) >= 0 else -1.0
            signed.append(sign * (ax * ax + ay * ay) ** 0.5)
        left = max(self.min_half, abs(min(signed)))
        right = max(self.min_half, abs(max(signed)))
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
