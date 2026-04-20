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

    def apply_foundation_offset(self, section: SectionData, foundation_thickness_m: float) -> SectionData:
        t = max(float(foundation_thickness_m), 0.0)
        if not section.project_z:
            section.base_z = []
            return section
        section.base_z = [z - t for z in section.project_z]
        return section

    def add_side_slopes(self, section: SectionData, cut_hv: float, fill_hv: float) -> SectionData:
        if not section.project_z or not section.terrain_z:
            return section
        w: WidthInfo = section.width_info or WidthInfo(0.0, 0.0, 0.0)
        # Reset esplicito: i segmenti esistono solo se la risoluzione corrente trova un intercetto valido.
        section.left_slope_segment = None
        section.right_slope_segment = None
        left_ok, left_outer, left_note, left_segment = self._apply_side_slope(
            section, -max(w.left_width, 0.0), cut_hv, fill_hv, left=True
        )
        right_ok, right_outer, right_note, right_segment = self._apply_side_slope(
            section, max(w.right_width, 0.0), cut_hv, fill_hv, left=False
        )
        section.side_slope_left_resolved = left_ok
        section.side_slope_right_resolved = right_ok
        # Alias richiesto per diagnostica/consumi esterni.
        section.left_slope_resolved = left_ok
        section.right_slope_resolved = right_ok
        section.left_slope_hit_offset = left_outer
        section.right_slope_hit_offset = right_outer
        section.side_slope_left_outer_offset = left_outer
        section.side_slope_right_outer_offset = right_outer
        section.side_slope_left_note = left_note
        section.side_slope_right_note = right_note
        section.left_slope_segment = left_segment
        section.right_slope_segment = right_segment
        if not section.side_slope_left_resolved:
            section.warnings.append("Scarpata sinistra approssimata: intercettazione terreno non trovata.")
        if not section.side_slope_right_resolved:
            section.warnings.append("Scarpata destra approssimata: intercettazione terreno non trovata.")
        return section

    def apply_effective_section_window(self, section: SectionData, max_section_width: float, section_buffer: float) -> SectionData:
        if not section.offsets or len(section.offsets) < 2:
            return section
        max_width = max(float(max_section_width), 0.1)
        buffer = max(float(section_buffer), 0.0)
        section.max_section_width = max_width
        section.section_buffer = buffer

        left_hit = section.left_slope_hit_offset if section.left_slope_resolved else None
        right_hit = section.right_slope_hit_offset if section.right_slope_resolved else None
        has_hits = left_hit is not None and right_hit is not None and math.isfinite(left_hit) and math.isfinite(right_hit)

        if has_hits:
            raw_left = min(float(left_hit), float(right_hit))
            raw_right = max(float(left_hit), float(right_hit))
            effective_left = raw_left - buffer
            effective_right = raw_right + buffer
            effective_width = max(0.0, effective_right - effective_left)
            rounded_width = math.ceil(effective_width / 10.0) * 10.0 if effective_width > 0.0 else 10.0
            final_width = min(max_width, rounded_width)
            center = 0.5 * (effective_left + effective_right)
            section.used_max_width_fallback = False
            section.effective_left_offset = effective_left
            section.effective_right_offset = effective_right
            section.effective_total_width = effective_width
        else:
            final_width = max_width
            center = 0.0
            section.used_max_width_fallback = True
            section.effective_left_offset = None
            section.effective_right_offset = None
            section.effective_total_width = max_width

        dom_left = float(section.offsets[0])
        dom_right = float(section.offsets[-1])
        dom_width = max(0.1, dom_right - dom_left)
        final_width = min(final_width, dom_width)
        final_left = center - final_width * 0.5
        final_right = center + final_width * 0.5
        if final_left < dom_left:
            shift = dom_left - final_left
            final_left += shift
            final_right += shift
        if final_right > dom_right:
            shift = final_right - dom_right
            final_left -= shift
            final_right -= shift
        final_left = max(dom_left, final_left)
        final_right = min(dom_right, final_right)
        if final_right <= final_left:
            final_left, final_right = dom_left, dom_right

        section.final_left_offset = final_left
        section.final_right_offset = final_right
        section.final_total_width = final_right - final_left
        self._clip_section_to_offsets(section, final_left, final_right)
        return section

    def _clip_section_to_offsets(self, section: SectionData, left: float, right: float) -> None:
        old_offsets = list(section.offsets)
        if len(old_offsets) < 2:
            return
        clipped_offsets = [left]
        clipped_offsets.extend(o for o in old_offsets if left < o < right)
        clipped_offsets.append(right)
        clipped_offsets = sorted(set(round(o, 6) for o in clipped_offsets))
        section.offsets = clipped_offsets
        section.terrain_z = [self._interp_piecewise(old_offsets, section.terrain_z, off) for off in clipped_offsets]
        section.project_z = [self._interp_piecewise(old_offsets, section.project_z, off) for off in clipped_offsets]
        if section.road_core_z:
            section.road_core_z = [self._interp_piecewise(old_offsets, section.road_core_z, off) for off in clipped_offsets]

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
    ) -> tuple[bool, float, str, tuple[tuple[float, float], tuple[float, float]] | None]:
        offsets = section.offsets
        terrain = section.terrain_z
        if len(offsets) < 2:
            return False, edge_offset, "Sezione troppo corta per risolvere la scarpata.", None

        tol = 1e-6
        min_x, max_x = offsets[0], offsets[-1]
        edge_x = min(max(edge_offset, min_x), max_x)
        edge_z = self._interp_piecewise(offsets, section.project_z, edge_x)
        terrain_edge = self._interp_piecewise(offsets, terrain, edge_x)
        if not (math.isfinite(edge_z) and math.isfinite(terrain_edge)):
            return False, edge_x, "Quota non valida sul bordo piattaforma.", None

        # cut: terreno sopra il bordo strada; fill: terreno sotto il bordo strada
        is_cut = terrain_edge > edge_z
        hv = max(cut_hv if is_cut else fill_hv, 1e-6)
        dir_out = -1.0 if left else 1.0
        dzdx = (1.0 if is_cut else -1.0) * dir_out / hv

        hit_x = self._find_first_outward_intersection(offsets, terrain, edge_x, edge_z, dzdx, left, tol)
        if hit_x is None:
            hit_x = self._fallback_outward_search(offsets, terrain, edge_x, edge_z, dzdx, left, tol)
        if hit_x is None:
            # Nessuna intercettazione trovata: NON collassare al terreno.
            # Estendi la scarpata fino al limite sezione.
            limit_x = min_x if left else max_x
            for i, x in enumerate(offsets):
                if self._is_outward_from_edge(x, edge_x, left, tol):
                    section.project_z[i] = edge_z + dzdx * (x - edge_x)
            slope_kind = "sterro" if is_cut else "riporto"
            return False, limit_x, f"Scarpata {slope_kind} non risolta; estesa fino al limite sezione.", None

        for i, x in enumerate(offsets):
            if not self._is_outward_from_edge(x, edge_x, left, tol):
                continue
            if (left and x >= hit_x - tol) or ((not left) and x <= hit_x + tol):
                section.project_z[i] = edge_z + dzdx * (x - edge_x)
            else:
                section.project_z[i] = terrain[i]
        hit_z = self._interp_piecewise(offsets, terrain, hit_x)
        slope_kind = "sterro" if is_cut else "riporto"
        if not math.isfinite(hit_z):
            return True, hit_x, f"Intercettazione terreno risolta ({slope_kind}).", None
        # Geometria della scarpata come singolo segmento: bordo piattaforma -> intercetto terreno.
        slope_segment = ((edge_x, edge_z), (hit_x, hit_z))
        return True, hit_x, f"Intercettazione terreno risolta ({slope_kind}).", slope_segment

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
                # Terreno e scarpata quasi paralleli: intercetta vertici quasi coincidenti.
                d0 = z0 - (edge_z + slope_m * (x0 - edge_x))
                d1 = z1 - (edge_z + slope_m * (x1 - edge_x))
                if abs(d0) <= 1e-3 and self._is_outward_from_edge(x0, edge_x, left, tol):
                    return x0
                if abs(d1) <= 1e-3 and self._is_outward_from_edge(x1, edge_x, left, tol):
                    return x1
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

    def _fallback_outward_search(
        self,
        offsets: List[float],
        terrain: List[float],
        edge_x: float,
        edge_z: float,
        slope_m: float,
        left: bool,
        tol: float,
    ) -> float | None:
        outward = [x for x in offsets if self._is_outward_from_edge(x, edge_x, left, tol)]
        if not outward:
            return None
        outward_sorted = sorted(outward, reverse=left)
        prev_x = edge_x
        prev_d = self._terrain_minus_slope(offsets, terrain, prev_x, edge_x, edge_z, slope_m)
        if not math.isfinite(prev_d):
            prev_d = 0.0
        for x in outward_sorted:
            if abs(x - edge_x) <= tol:
                continue
            d = self._terrain_minus_slope(offsets, terrain, x, edge_x, edge_z, slope_m)
            if not math.isfinite(d):
                prev_x, prev_d = x, d
                continue
            # Hit quasi su vertice campionato.
            if abs(d) <= 1e-3:
                return x
            if math.isfinite(prev_d) and (d * prev_d < 0.0):
                # Oscillazioni locali: usa interpolazione lineare su diff(x).
                den = d - prev_d
                if abs(den) <= 1e-12:
                    return x
                t = -prev_d / den
                t = max(0.0, min(1.0, t))
                return prev_x + (x - prev_x) * t
            prev_x, prev_d = x, d
        return None

    def _terrain_minus_slope(
        self,
        offsets: List[float],
        terrain: List[float],
        x: float,
        edge_x: float,
        edge_z: float,
        slope_m: float,
    ) -> float:
        terr = self._interp_piecewise(offsets, terrain, x)
        slp = edge_z + slope_m * (x - edge_x)
        return terr - slp

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
