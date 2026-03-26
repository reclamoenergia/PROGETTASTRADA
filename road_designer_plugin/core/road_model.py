from __future__ import annotations

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
        return section

    def add_side_slopes(self, section: SectionData, cut_hv: float, fill_hv: float) -> SectionData:
        if not section.project_z or not section.terrain_z:
            return section
        left_i = 0
        right_i = len(section.offsets) - 1
        # v1: usa estremi già campionati; assume lunghezza sezione sufficiente
        section.project_z[left_i] = self._slope_to_terrain(
            section.offsets[left_i],
            section.project_z[left_i],
            section.offsets[left_i + 1],
            section.project_z[left_i + 1],
            section.terrain_z[left_i],
            cut_hv,
            fill_hv,
            True,
        )
        section.project_z[right_i] = self._slope_to_terrain(
            section.offsets[right_i],
            section.project_z[right_i],
            section.offsets[right_i - 1],
            section.project_z[right_i - 1],
            section.terrain_z[right_i],
            cut_hv,
            fill_hv,
            False,
        )
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

    def _slope_to_terrain(self, x0: float, z0: float, x1: float, z1: float, terrain_edge: float, cut_hv: float, fill_hv: float, left: bool) -> float:
        dz = terrain_edge - z0
        if dz < 0:
            m = 1.0 / max(cut_hv, 1e-6)
        else:
            m = 1.0 / max(fill_hv, 1e-6)
        dx = abs(x1 - x0)
        z_ext = z1 + m * dx
        return terrain_edge if abs(terrain_edge - z_ext) < abs(terrain_edge - z0) else z_ext
