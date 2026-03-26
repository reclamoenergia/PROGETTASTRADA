from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from qgis.core import QgsVectorLayer

from .models import ProfileData
from ..utils.math_utils import clamp


class VerticalProfileBuilder:
    def build(
        self,
        progressive: List[float],
        terrain_z: List[float],
        max_slope_pct: float,
        min_vertical_radius: float,
        forced_points_layer: Optional[QgsVectorLayer] = None,
    ) -> ProfileData:
        z = terrain_z.copy()
        forced = self._forced_by_progressive(progressive, forced_points_layer)
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
    ) -> Dict[int, float]:
        if not forced_layer or forced_layer.fields().indexFromName("z") < 0:
            return {}
        idx = forced_layer.fields().indexFromName("z")
        feats = list(forced_layer.getFeatures())
        if not feats:
            return {}
        out: Dict[int, float] = {}
        n = len(progressive)
        for f in feats:
            p = f.geometry().asPoint()
            # fallback v1: associa i punti in ordine alle progressive
            k = int(round((len(out) / max(1, len(feats) - 1)) * (n - 1)))
            out[k] = float(f[idx])
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
