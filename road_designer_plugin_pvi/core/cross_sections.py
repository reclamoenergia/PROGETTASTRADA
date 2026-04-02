from __future__ import annotations

import math
from typing import List

from qgis.core import QgsGeometry

from .alignment import Alignment
from .models import SectionData
from .terrain_sampler import TerrainSampler
from ..utils.geometry_utils import line_from_point_dir, normalize, perpendicular


class CrossSectionGenerator:
    def generate(
        self,
        alignment: Alignment,
        terrain: TerrainSampler,
        section_step: float,
        section_length: float,
        sample_step: float,
    ) -> List[SectionData]:
        sections: List[SectionData] = []
        if alignment.length <= 0:
            return sections
        prog = 0.0
        idx = 0
        while prog <= alignment.length + 1e-6:
            p, tan = alignment.point_and_tangent_at(prog)
            nor = perpendicular(tan[0], tan[1])
            nor = normalize(nor[0], nor[1])
            half = section_length / 2.0
            offsets = []
            terrain_z = []
            off = -half
            while off <= half + 1e-9:
                x = p[0] + nor[0] * off
                y = p[1] + nor[1] * off
                offsets.append(off)
                terrain_z.append(terrain.sample_point(x, y))
                off += sample_step
            sections.append(
                SectionData(
                    index=idx,
                    progressive=prog,
                    axis_point=p,
                    tangent=tan,
                    normal=nor,
                    offsets=offsets,
                    terrain_z=terrain_z,
                )
            )
            idx += 1
            prog += section_step
        return sections

    def as_geometry(self, section: SectionData) -> QgsGeometry:
        half = max(abs(section.offsets[0]), abs(section.offsets[-1]))
        return line_from_point_dir(section.axis_point, section.normal, half)
