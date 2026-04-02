from __future__ import annotations

import math
from typing import Iterable, List, Tuple

from qgis.core import QgsPointXY, QgsRaster, QgsRasterLayer


class TerrainSampler:
    def __init__(self, raster_layer: QgsRasterLayer):
        self.raster = raster_layer
        self.provider = raster_layer.dataProvider()

    def sample_point(self, x: float, y: float) -> float:
        pt = QgsPointXY(x, y)
        if not self.raster.extent().contains(pt):
            return float("nan")
        result = self.provider.identify(QgsPointXY(x, y), QgsRaster.IdentifyFormatValue)
        if not result.isValid():
            return float("nan")
        values = result.results()
        if not values:
            return float("nan")
        value = float(values.get(1, list(values.values())[0]))
        nodata = self.provider.sourceNoDataValue(1) if self.provider.sourceHasNoDataValue(1) else None
        if nodata is not None and abs(value - nodata) < 1e-9:
            return float("nan")
        if not math.isfinite(value):
            return float("nan")
        return value

    def sample_many(self, points: Iterable[Tuple[float, float]]) -> List[float]:
        samples = [self.sample_point(x, y) for x, y in points]
        invalid = [i for i, z in enumerate(samples) if not math.isfinite(z)]
        if not invalid:
            return samples
        total = max(1, len(samples))
        if len(invalid) > 5 and (len(invalid) / total) > 0.2:
            raise ValueError(
                f"Campionamento DTM non valido in {len(invalid)}/{total} punti: verificare estensione raster e NoData."
            )
        valid_idx = [i for i, z in enumerate(samples) if math.isfinite(z)]
        if not valid_idx:
            raise ValueError("Campionamento DTM completamente non valido (tutti i punti NoData/fuori estensione).")
        for i in invalid:
            prev_candidates = [j for j in valid_idx if j < i]
            next_candidates = [j for j in valid_idx if j > i]
            if prev_candidates and next_candidates:
                j0 = prev_candidates[-1]
                j1 = next_candidates[0]
                t = (i - j0) / (j1 - j0)
                samples[i] = samples[j0] + (samples[j1] - samples[j0]) * t
            elif prev_candidates:
                samples[i] = samples[prev_candidates[-1]]
            else:
                samples[i] = samples[next_candidates[0]]
        return samples
