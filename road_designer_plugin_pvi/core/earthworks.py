from __future__ import annotations

from typing import List

from .models import EarthworkInterval, EarthworkResult, SectionData
from ..utils.math_utils import diff_signed_segments


class EarthworksCalculator:
    def compute_section_areas(self, section: SectionData) -> SectionData:
        if not section.project_z or not section.terrain_z:
            return section
        reference = section.base_z if section.base_z else section.project_z
        diff = [rz - tz for rz, tz in zip(reference, section.terrain_z)]
        cut, fill = diff_signed_segments(section.offsets, diff)
        foundation_diff = [pz - bz for pz, bz in zip(section.project_z, reference)]
        _foundation_cut, foundation_fill = diff_signed_segments(section.offsets, foundation_diff)
        section.cut_area = cut
        section.fill_area = fill
        section.foundation_area = foundation_fill
        return section

    def compute_volumes(self, sections: List[SectionData]) -> EarthworkResult:
        intervals: List[EarthworkInterval] = []
        cum_cut = 0.0
        cum_fill = 0.0
        for i in range(1, len(sections)):
            s0, s1 = sections[i - 1], sections[i]
            ds = s1.progressive - s0.progressive
            cut_v = ds * (s0.cut_area + s1.cut_area) / 2.0
            fill_v = ds * (s0.fill_area + s1.fill_area) / 2.0
            cum_cut += cut_v
            cum_fill += fill_v
            intervals.append(
                EarthworkInterval(
                    section_i=s0.index,
                    section_f=s1.index,
                    progressive_i=s0.progressive,
                    progressive_f=s1.progressive,
                    cut_area_i=s0.cut_area,
                    cut_area_f=s1.cut_area,
                    fill_area_i=s0.fill_area,
                    fill_area_f=s1.fill_area,
                    cut_volume=cut_v,
                    fill_volume=fill_v,
                    cum_cut=cum_cut,
                    cum_fill=cum_fill,
                )
            )
        cum_foundation = 0.0
        for i in range(1, len(sections)):
            s0, s1 = sections[i - 1], sections[i]
            ds = s1.progressive - s0.progressive
            f_v = ds * (s0.foundation_area + s1.foundation_area) / 2.0
            cum_foundation += f_v
        return EarthworkResult(intervals=intervals, total_cut=cum_cut, total_fill=cum_fill, total_foundation=cum_foundation)
