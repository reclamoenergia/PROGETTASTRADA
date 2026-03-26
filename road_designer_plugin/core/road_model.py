from __future__ import annotations

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
        section.side_slope_left_resolved = self._apply_side_slope(section, -max(w.left_width, 0.0), cut_hv, fill_hv, left=True)
        section.side_slope_right_resolved = self._apply_side_slope(section, max(w.right_width, 0.0), cut_hv, fill_hv, left=False)
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

    def _apply_side_slope(self, section: SectionData, edge_offset: float, cut_hv: float, fill_hv: float, left: bool) -> bool:
        offsets = section.offsets
        if len(offsets) < 2:
            return False
        edge_i = min(range(len(offsets)), key=lambda i: abs(offsets[i] - edge_offset))
        edge_x = offsets[edge_i]
        edge_z = section.project_z[edge_i]
        terrain_edge = section.terrain_z[edge_i]
        if not math.isfinite(edge_z) or not math.isfinite(terrain_edge):
            return False

        # cut: terreno sopra il bordo strada; fill: terreno sotto il bordo strada
        is_cut = terrain_edge > edge_z
        hv = max(cut_hv if is_cut else fill_hv, 1e-6)
        dir_out = -1.0 if left else 1.0
        dzdx = (1.0 if is_cut else -1.0) * dir_out / hv

        indices = range(edge_i - 1, -1, -1) if left else range(edge_i + 1, len(offsets))
        prev_x, prev_diff = edge_x, edge_z - terrain_edge
        hit_i = None
        hit_x = edge_x
        hit_z = edge_z

        for i in indices:
            x = offsets[i]
            z_line = edge_z + dzdx * (x - edge_x)
            terr = section.terrain_z[i]
            if not math.isfinite(terr):
                continue
            diff = z_line - terr
            if abs(diff) <= 1e-6 or (diff > 0) != (prev_diff > 0):
                t = 0.0 if abs(x - prev_x) < 1e-9 else (0.0 - prev_diff) / (diff - prev_diff)
                t = max(0.0, min(1.0, t))
                hit_x = prev_x + (x - prev_x) * t
                hit_z = edge_z + dzdx * (hit_x - edge_x)
                hit_i = i
                break
            prev_x, prev_diff = x, diff

        if hit_i is None:
            # fallback controllato: estensione limitata (non fino al bordo sezione)
            max_ext = 20.0
            for i in indices:
                x = offsets[i]
                if abs(x - edge_x) <= max_ext + 1e-6:
                    section.project_z[i] = edge_z + dzdx * (x - edge_x)
                else:
                    section.project_z[i] = section.terrain_z[i]
            return False

        for i in indices:
            x = offsets[i]
            if (left and x >= hit_x) or ((not left) and x <= hit_x):
                section.project_z[i] = edge_z + dzdx * (x - edge_x)
            else:
                section.project_z[i] = section.terrain_z[i]
        return True
