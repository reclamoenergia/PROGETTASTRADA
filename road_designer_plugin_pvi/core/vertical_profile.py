from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from qgis.core import QgsGeometry, QgsPointXY, QgsVectorLayer

from .models import ProfileData, PviRow
from ..utils.math_utils import clamp


@dataclass
class PviLoadResult:
    rows: List[PviRow]
    warnings: List[str]


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

    def build_from_pvi(self, progressive: Sequence[float], terrain_z: Sequence[float], pvi_rows: Sequence[PviRow]) -> ProfileData:
        rows = [r for r in pvi_rows if r.enabled]
        if len(rows) < 2:
            raise ValueError("Servono almeno 2 PVI validi per costruire il profilo.")
        rows = sorted(rows, key=lambda r: r.progressive)

        proj: List[float] = []
        for s in progressive:
            proj.append(self._interpolate_project_z(float(s), rows))
        return ProfileData(progressive=list(progressive), terrain_z=list(terrain_z), project_z=proj)

    def load_pvi_rows(
        self,
        layer: Optional[QgsVectorLayer],
        axis_points: Sequence[Tuple[float, float]],
        elevation_field: str,
        curve_field: str,
        default_curve_length: float,
    ) -> PviLoadResult:
        warnings: List[str] = []
        if not layer:
            return PviLoadResult(rows=[], warnings=["Layer PVI non selezionato."])
        if not axis_points:
            return PviLoadResult(rows=[], warnings=["Asse non disponibile: impossibile proiettare i PVI."])

        e_idx = layer.fields().indexFromName(elevation_field)
        if e_idx < 0:
            return PviLoadResult(rows=[], warnings=["Campo quota PVI non valido."])
        c_idx = layer.fields().indexFromName(curve_field) if curve_field else -1

        axis_geom = QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in axis_points])
        if axis_geom.isEmpty() or axis_geom.length() <= 0:
            return PviLoadResult(rows=[], warnings=["Geometria asse non valida."])

        rows: List[PviRow] = []
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom.isEmpty():
                continue
            try:
                pt = geom.asPoint()
                z = float(feat[e_idx])
            except Exception:
                warnings.append(f"Feature PVI {feat.id()} ignorata: quota non valida.")
                continue

            curve_len = float(default_curve_length)
            if c_idx >= 0:
                val = feat[c_idx]
                if val not in (None, ""):
                    try:
                        curve_len = float(val)
                    except Exception:
                        warnings.append(f"Feature PVI {feat.id()} con lunghezza curva non valida: default applicato.")

            nearest = axis_geom.nearestPoint(QgsGeometry.fromPointXY(QgsPointXY(pt.x(), pt.y())))
            if nearest.isEmpty():
                continue
            s = float(axis_geom.lineLocatePoint(nearest))
            rows.append(
                PviRow(
                    feature_id=int(feat.id()),
                    progressive=s,
                    elevation=z,
                    curve_length=max(0.0, curve_len),
                    enabled=True,
                    source_label=str(feat.id()),
                )
            )

        rows.sort(key=lambda r: r.progressive)
        near_eps = 1e-3
        for i in range(1, len(rows)):
            if abs(rows[i].progressive - rows[i - 1].progressive) <= near_eps:
                warnings.append(
                    "Progressive duplicate/quasi duplicate rilevate "
                    f"({rows[i - 1].progressive:.3f} m e {rows[i].progressive:.3f} m)."
                )
        if len(rows) < 2:
            warnings.append("Servono almeno 2 PVI validi dopo il caricamento.")

        return PviLoadResult(rows=rows, warnings=warnings)

    def recompute_pvi_diagnostics(self, rows: Sequence[PviRow], max_slope_pct: float) -> List[PviRow]:
        max_slope = max_slope_pct / 100.0
        out = sorted([r for r in rows], key=lambda r: r.progressive)
        for i, row in enumerate(out):
            warn = []
            if row.curve_length < 0:
                warn.append("L curva < 0")
            if i > 0:
                ds = row.progressive - out[i - 1].progressive
                if ds <= 1e-9:
                    warn.append("Progressiva duplicata")
                else:
                    slope = (row.elevation - out[i - 1].elevation) / ds
                    if abs(slope) > max_slope + 1e-6:
                        warn.append("Pendenza > limite")
            row.warning = "; ".join(warn)
        return out

    def incoming_slope_pct(self, rows: Sequence[PviRow], idx: int) -> Optional[float]:
        if idx <= 0 or idx >= len(rows):
            return None
        ds = rows[idx].progressive - rows[idx - 1].progressive
        if ds <= 1e-9:
            return None
        return (rows[idx].elevation - rows[idx - 1].elevation) / ds * 100.0

    def outgoing_slope_pct(self, rows: Sequence[PviRow], idx: int) -> Optional[float]:
        if idx < 0 or idx >= len(rows) - 1:
            return None
        ds = rows[idx + 1].progressive - rows[idx].progressive
        if ds <= 1e-9:
            return None
        return (rows[idx + 1].elevation - rows[idx].elevation) / ds * 100.0

    def _interpolate_project_z(self, s: float, rows: Sequence[PviRow]) -> float:
        if s <= rows[0].progressive:
            return rows[0].elevation
        if s >= rows[-1].progressive:
            return rows[-1].elevation
        for i in range(1, len(rows)):
            r0, r1 = rows[i - 1], rows[i]
            if r1.progressive >= s:
                ds = r1.progressive - r0.progressive
                if ds <= 1e-9:
                    return r1.elevation
                t = (s - r0.progressive) / ds
                # Hook per futura curva verticale: sostituire interpolazione lineare.
                return r0.elevation + (r1.elevation - r0.elevation) * t
        return rows[-1].elevation

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
