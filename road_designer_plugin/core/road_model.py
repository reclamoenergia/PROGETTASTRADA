from __future__ import annotations

import bisect
import math
from typing import List

from .models import ProfileData, SectionData, WidthInfo


class RoadModelBuilder:
    def build_section_profile(
        self,
        section: SectionData,
        profile: ProfileData,
        min_platform_width: float,
        crossfall_pct: float,
        pad_slope_pct: float,
    ) -> SectionData:
        axis_z = self._project_z_for_progressive(profile, section.progressive)
        half_core = min_platform_width / 2.0
        cf = crossfall_pct / 100.0
        pad_s = pad_slope_pct / 100.0
        w: WidthInfo = section.width_info or WidthInfo(half_core, half_core, min_platform_width)
        project_z: List[float] = []
        core_z: List[float] = []
        for idx, off in enumerate(section.offsets):
            if off < -half_core:
                edge = axis_z - cf * half_core
                z = edge + pad_s * (abs(off) - half_core)
            elif off > half_core:
                edge = axis_z - cf * half_core
                z = edge + pad_s * (off - half_core)
            else:
                z = axis_z - cf * abs(off)
            if off < -w.left_width or off > w.right_width:
                z = section.terrain_z[idx]
            project_z.append(z)
            core_z.append(axis_z - cf * abs(max(-half_core, min(half_core, off))))
        section.project_z = project_z
        section.road_core_z = core_z
        section.road_core_left_offset = -half_core
        section.crown_offset = 0.0
        section.road_core_right_offset = half_core
        return section

    def add_side_slopes(self, section: SectionData, cut_hv: float, fill_hv: float) -> SectionData:
        if not section.project_z or not section.terrain_z:
            return section
        w: WidthInfo = section.width_info or WidthInfo(0.0, 0.0, 0.0)
        left_ok, left_outer, left_note = self._apply_side_slope(
            section, -max(w.left_width, 0.0), cut_hv, fill_hv, left=True
        )
        right_ok, right_outer, right_note = self._apply_side_slope(
            section, max(w.right_width, 0.0), cut_hv, fill_hv, left=False
        )
        section.side_slope_left_resolved = left_ok
        section.side_slope_right_resolved = right_ok
        section.side_slope_left_outer_offset = left_outer
        section.side_slope_right_outer_offset = right_outer
        section.side_slope_left_note = left_note
        section.side_slope_right_note = right_note
        if not section.side_slope_left_resolved:
            section.warnings.append("Scarpata sinistra approssimata: intercettazione terreno non trovata.")
        if not section.side_slope_right_resolved:
            section.warnings.append("Scarpata destra approssimata: intercettazione terreno non trovata.")
        return section

    def _project_z_for_progressive(self, profile: ProfileData, prog: float) -> float:
        s = profile.progressive
        z = profile.project_z
        if prog <= s[0]:
            return z[0]
        if prog >= s[-1]:
            return z[-1]
        for i in range(1, len(s)):
            if s[i] >= prog:
                t = (prog - s[i - 1]) / (s[i] - s[i - 1])
                return z[i - 1] + (z[i] - z[i - 1]) * t
        return z[-1]

    def _apply_side_slope(
        self, section: SectionData, edge_offset: float, cut_hv: float, fill_hv: float, left: bool
    ) -> tuple[bool, float, str]:
        offsets = section.offsets
        terrain = section.terrain_z
        if len(offsets) < 2:
            return False, edge_offset, "Sezione troppo corta per risolvere la scarpata."

        tol = 1e-6
        min_x, max_x = offsets[0], offsets[-1]
        edge_x = min(max(edge_offset, min_x), max_x)
        edge_z = self._interp_piecewise(offsets, section.project_z, edge_x)
        terrain_edge = self._interp_piecewise(offsets, terrain, edge_x)
        if not (math.isfinite(edge_z) and math.isfinite(terrain_edge)):
            return False, edge_x, "Quota non valida sul bordo piattaforma."

        # cut: terreno sopra il bordo strada; fill: terreno sotto il bordo strada
        is_cut = terrain_edge > edge_z
        hv = max(cut_hv if is_cut else fill_hv, 1e-6)
        dir_out = -1.0 if left else 1.0
        dzdx = (1.0 if is_cut else -1.0) * dir_out / hv

        hit_x = self._find_first_outward_intersection(offsets, terrain, edge_x, edge_z, dzdx, left, tol)
        if hit_x is None:
            max_ext = 20.0
            available = (edge_x - min_x) if left else (max_x - edge_x)
            ext = max(0.0, min(max_ext, available))
            limit_x = edge_x - ext if left else edge_x + ext
            for i, x in enumerate(offsets):
                if self._is_outward_from_edge(x, edge_x, left, tol) and abs(x - edge_x) <= ext + tol:
                    section.project_z[i] = edge_z + dzdx * (x - edge_x)
                elif self._is_outward_from_edge(x, edge_x, left, tol):
                    section.project_z[i] = terrain[i]
            slope_kind = "sterro" if is_cut else "riporto"
            return False, limit_x, f"Scarpata {slope_kind} non risolta; fallback limitato a {ext:.1f} m."

        for i, x in enumerate(offsets):
            if not self._is_outward_from_edge(x, edge_x, left, tol):
                continue
            if (left and x >= hit_x - tol) or ((not left) and x <= hit_x + tol):
                section.project_z[i] = edge_z + dzdx * (x - edge_x)
            else:
                section.project_z[i] = terrain[i]
        slope_kind = "sterro" if is_cut else "riporto"
        return True, hit_x, f"Intercettazione terreno risolta ({slope_kind})."

    def _find_first_outward_intersection(
        self,
        offsets: List[float],
        terrain: List[float],
        edge_x: float,
        edge_z: float,
        slope_m: float,
        left: bool,
        tol: float,
    ) -> float | None:
        n = len(offsets)
        pos = bisect.bisect_left(offsets, edge_x)
        seg_indices: List[tuple[int, int]] = []

        if left:
            hi = min(pos, n - 1)
            if pos < n and abs(offsets[pos] - edge_x) <= tol:
                hi = pos
            while hi >= 1:
                seg_indices.append((hi - 1, hi))
                hi -= 1
        else:
            if pos >= n:
                return None
            if pos < n and abs(offsets[pos] - edge_x) <= tol:
                lo = pos
            else:
                lo = max(0, pos - 1)
            while lo < n - 1:
                seg_indices.append((lo, lo + 1))
                lo += 1

        for i0, i1 in seg_indices:
            x0, x1 = offsets[i0], offsets[i1]
            z0, z1 = terrain[i0], terrain[i1]
            if not (math.isfinite(z0) and math.isfinite(z1)):
                continue
            dx = x1 - x0
            if abs(dx) <= tol:
                continue
            mt = (z1 - z0) / dx
            den = slope_m - mt
            if abs(den) <= 1e-9:
                continue
            x_hit = (z0 - edge_z + slope_m * edge_x - mt * x0) / den
            seg_min = min(x0, x1) - tol
            seg_max = max(x0, x1) + tol
            if x_hit < seg_min or x_hit > seg_max:
                continue
            if not self._is_outward_from_edge(x_hit, edge_x, left, tol):
                continue
            return x_hit
        return None

    def _interp_piecewise(self, xs: List[float], ys: List[float], x: float) -> float:
        if not xs or not ys:
            return float("nan")
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = bisect.bisect_left(xs, x)
        if i < len(xs) and abs(xs[i] - x) <= 1e-9:
            return ys[i]
        x0, x1 = xs[i - 1], xs[i]
        y0, y1 = ys[i - 1], ys[i]
        dx = x1 - x0
        if abs(dx) <= 1e-12:
            return y0
        t = (x - x0) / dx
        return y0 + (y1 - y0) * t

    def _is_outward_from_edge(self, x: float, edge_x: float, left: bool, tol: float) -> bool:
        if left:
            return x <= edge_x + tol
        return x >= edge_x - tol
