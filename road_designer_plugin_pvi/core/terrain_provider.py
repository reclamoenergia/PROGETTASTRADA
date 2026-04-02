from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List, Sequence, Tuple

Point2D = Tuple[float, float]


class TerrainProvider(ABC):
    @abstractmethod
    def get_elevation(self, x: float, y: float) -> float:
        raise NotImplementedError

    def sample_along_points(self, points: Iterable[Point2D]) -> List[float]:
        return [self.get_elevation(x, y) for x, y in points]

    def sample_along_line(self, line_points: Sequence[Point2D], step: float) -> List[Tuple[float, float, float, float]]:
        if not line_points:
            return []
        if len(line_points) == 1 or step <= 0:
            x, y = line_points[0]
            return [(0.0, x, y, self.get_elevation(x, y))]

        samples: List[Tuple[float, float, float, float]] = []
        progressive = 0.0
        samples.append((progressive, line_points[0][0], line_points[0][1], self.get_elevation(*line_points[0])))
        carry = 0.0
        for i in range(1, len(line_points)):
            x0, y0 = line_points[i - 1]
            x1, y1 = line_points[i]
            dx = x1 - x0
            dy = y1 - y0
            seg_len = (dx * dx + dy * dy) ** 0.5
            if seg_len <= 1e-9:
                continue
            ux = dx / seg_len
            uy = dy / seg_len
            cur = step - carry
            while cur < seg_len + 1e-12:
                x = x0 + ux * cur
                y = y0 + uy * cur
                samples.append((progressive + cur, x, y, self.get_elevation(x, y)))
                cur += step
            progressive += seg_len
            carry = seg_len - (cur - step)
        if (samples[-1][1], samples[-1][2]) != line_points[-1]:
            x, y = line_points[-1]
            samples.append((progressive, x, y, self.get_elevation(x, y)))
        return samples
