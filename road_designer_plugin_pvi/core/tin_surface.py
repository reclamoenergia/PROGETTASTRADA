from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsRectangle, QgsSpatialIndex

Point3D = Tuple[float, float, float]


@dataclass
class TriangleRecord:
    vertex_indices: Tuple[int, int, int]
    bbox: QgsRectangle
    geometry: QgsGeometry


class TinSurface:
    def __init__(self, vertices: Sequence[Point3D], triangles: Sequence[Tuple[int, int, int]]):
        self.vertices: List[Point3D] = list(vertices)
        self.triangles: List[TriangleRecord] = []
        self._index = QgsSpatialIndex()
        self._triangle_by_fid = {}

        for idx, tri in enumerate(triangles):
            pts = [QgsPointXY(self.vertices[i][0], self.vertices[i][1]) for i in tri]
            geom = QgsGeometry.fromPolygonXY([[pts[0], pts[1], pts[2], pts[0]]])
            if geom.isEmpty() or geom.area() <= 1e-10:
                continue
            bbox = geom.boundingBox()
            rec = TriangleRecord(vertex_indices=tri, bbox=bbox, geometry=geom)
            self.triangles.append(rec)
            feat = QgsFeature(idx)
            feat.setGeometry(geom)
            self._index.addFeature(feat)
            self._triangle_by_fid[idx] = rec

    def is_valid(self) -> bool:
        return len(self.vertices) >= 3 and len(self.triangles) > 0

    def get_elevation(self, x: float, y: float) -> float:
        query = QgsRectangle(x, y, x, y)
        candidates = self._index.intersects(query)
        p = QgsPointXY(x, y)
        for fid in candidates:
            tri = self._triangle_by_fid.get(fid)
            if not tri:
                continue
            if not tri.geometry.boundingBox().contains(p):
                continue
            if not tri.geometry.contains(QgsGeometry.fromPointXY(p)) and tri.geometry.distance(QgsGeometry.fromPointXY(p)) > 1e-8:
                continue
            z = self._interpolate_triangle(tri, x, y)
            if math.isfinite(z):
                return z
        return float("nan")

    def sample_along_points(self, points: Sequence[Tuple[float, float]]) -> List[float]:
        return [self.get_elevation(x, y) for x, y in points]

    def _interpolate_triangle(self, triangle: TriangleRecord, x: float, y: float) -> float:
        i0, i1, i2 = triangle.vertex_indices
        x0, y0, z0 = self.vertices[i0]
        x1, y1, z1 = self.vertices[i1]
        x2, y2, z2 = self.vertices[i2]

        det = ((y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2))
        if abs(det) < 1e-12:
            return float("nan")

        l1 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / det
        l2 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / det
        l3 = 1.0 - l1 - l2
        return l1 * z0 + l2 * z1 + l3 * z2
