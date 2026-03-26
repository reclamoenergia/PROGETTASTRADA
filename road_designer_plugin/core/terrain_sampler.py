from __future__ import annotations

from typing import Iterable, List, Tuple

from qgis.core import QgsPointXY, QgsRaster, QgsRasterLayer


class TerrainSampler:
    def __init__(self, raster_layer: QgsRasterLayer):
        self.raster = raster_layer
        self.provider = raster_layer.dataProvider()

    def sample_point(self, x: float, y: float) -> float:
        result = self.provider.identify(QgsPointXY(x, y), QgsRaster.IdentifyFormatValue)
        if not result.isValid():
            return float("nan")
        values = result.results()
        if not values:
            return float("nan")
        return float(values.get(1, list(values.values())[0]))

    def sample_many(self, points: Iterable[Tuple[float, float]]) -> List[float]:
        return [self.sample_point(x, y) for x, y in points]
