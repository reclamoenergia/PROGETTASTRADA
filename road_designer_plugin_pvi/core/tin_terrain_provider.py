from __future__ import annotations

from typing import Iterable, List, Tuple

from .terrain_provider import TerrainProvider
from .tin_surface import TinSurface


class TinTerrainProvider(TerrainProvider):
    def __init__(self, surface: TinSurface):
        self.surface = surface

    def get_elevation(self, x: float, y: float) -> float:
        return self.surface.get_elevation(x, y)

    def sample_many(self, points: Iterable[Tuple[float, float]]) -> List[float]:
        return self.surface.sample_along_points(list(points))
