from __future__ import annotations

import math
import logging
from typing import Dict, List, Optional

from qgis.core import QgsGeometry, QgsPointXY, QgsVectorLayer

from .models import ProfileData
from ..utils.math_utils import clamp


class VerticalProfileBuilder:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def build(
        self,
        progressive: List[float],
        terrain_z: List[float],
        max_slope_pct: float,
        min_vertical_radius: float,
        forced_points_layer: Optional[QgsVectorLayer] = None,
        axis_points: Optional[List[tuple[float, float]]] = None,
    ) -> ProfileData:
        z = terrain_z.copy()
        forced = self._forced_by_progressive(progressive, forced_points_layer, axis_points)
        for i, zp in forced.items():
            z[i] = zp
        max_slope = max_slope_pct / 100.0
        z = self._limit_slopes(progressive, z, max_slope)
        z = self._apply_vertical_smoothing(progressive, z, min_vertical_radius)
        for i, zp in forced.items():
            z[i] = zp
        z = self._limit_slopes(progressive, z, max_slope)
        return ProfileData(progressive=progressive, terrain_z=terrain_z, project_z=z)

    def _forced_by_progressive(
        self,
        progressive: List[float],
        forced_layer: Optional[QgsVectorLayer],
        axis_points: Optional[List[tuple[float, float]]],
    ) -> Dict[int, float]:
        if not forced_layer or forced_layer.fields().indexFromName("z") < 0 or not axis_points:
            return {}

        idx = forced_layer.fields().indexFromName("z")
        feats = list(forced_layer.getFeatures())
        if not feats or not progressive:
            return {}

        axis_geom = QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in axis_points])
        if axis_geom.isEmpty() or axis_geom.length() <= 0:
            return {}

        step_guess = progressive[1] - progressive[0] if len(progressive) > 1 else 5.0
        max_distance = max(5.0, step_guess * 3.0)

        out: Dict[int, float] = {}
        out_dist: Dict[int, float] = {}
        n = len(progressive)
        for f in sorted(feats, key=lambda ft: ft.id()):
            geom = f.geometry()
            if geom.isEmpty():
                continue

            try:
                pt = geom.asPoint()
            except Exception:
                continue

            try:
                z_forced = float(f[idx])
            except Exception:
                self.logger.warning("Forced point %s skipped: invalid z value.", f.id())
                continue

            nearest = axis_geom.nearestPoint(QgsGeometry.fromPointXY(QgsPointXY(pt.x(), pt.y())))
            if nearest.isEmpty():
                continue
            np = nearest.asPoint()
            dist = math.dist((pt.x(), pt.y()), (np.x(), np.y()))
            if dist > max_distance:
                self.logger.warning(
                    "Forced point %s ignored: %.2f m away from axis (max %.2f m).",
                    f.id(),
                    dist,
                    max_distance,
                )
                continue

            target_progressive = axis_geom.lineLocatePoint(QgsGeometry.fromPointXY(np))
            k = 0 if target_progressive <= progressive[0] else n - 1 if target_progressive >= progressive[-1] else min(
                range(n), key=lambda i: abs(progressive[i] - target_progressive)
            )
            if k not in out or dist <= out_dist[k]:
                out[k] = z_forced
                out_dist[k] = dist

        return out

    def _limit_slopes(self, s: List[float], z: List[float], max_slope: float) -> List[float]:
        out = z.copy()
        for i in range(1, len(out)):
            ds = s[i] - s[i - 1]
            if ds <= 0:
                continue
            dz = out[i] - out[i - 1]
            lim = max_slope * ds
            out[i] = out[i - 1] + clamp(dz, -lim, lim)

        for i in range(len(out) - 2, -1, -1):
            ds = s[i + 1] - s[i]
            if ds <= 0:
                continue
            dz = out[i] - out[i + 1]
            lim = max_slope * ds
            out[i] = out[i + 1] + clamp(dz, -lim, lim)

        return out

    def _apply_vertical_smoothing(self, s: List[float], z: List[float], min_radius: float) -> List[float]:
        if len(z) < 3:
            return z

        out = z.copy()

        # v1 semplificato: filtro su cambio pendenza equivalente a raggio minimo
        for i in range(1, len(out) - 1):
            ds0 = max(1e-6, s[i] - s[i - 1])
            ds1 = max(1e-6, s[i + 1] - s[i])
            g0 = (out[i] - out[i - 1]) / ds0
            g1 = (out[i + 1] - out[i]) / ds1
            dg = g1 - g0
            ds = (ds0 + ds1) / 2
            max_dg = ds / max(min_radius, 1.0)

            if abs(dg) > max_dg:
                target_g1 = g0 + math.copysign(max_dg, dg)
                out[i + 1] = out[i] + target_g1 * ds1

        return out
