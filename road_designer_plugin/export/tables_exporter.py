from __future__ import annotations

import csv
from pathlib import Path

from ..core.models import EarthworkResult


class TablesExporter:
    def export_volumes_csv(self, path: str, result: EarthworkResult) -> str:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "sezione_iniziale",
                    "sezione_finale",
                    "progressiva_iniziale",
                    "progressiva_finale",
                    "area_sterro_i",
                    "area_sterro_f",
                    "area_riporto_i",
                    "area_riporto_f",
                    "volume_sterro",
                    "volume_riporto",
                    "cumulato_sterro",
                    "cumulato_riporto",
                ]
            )
            for it in result.intervals:
                w.writerow(
                    [
                        it.section_i,
                        it.section_f,
                        f"{it.progressive_i:.3f}",
                        f"{it.progressive_f:.3f}",
                        f"{it.cut_area_i:.3f}",
                        f"{it.cut_area_f:.3f}",
                        f"{it.fill_area_i:.3f}",
                        f"{it.fill_area_f:.3f}",
                        f"{it.cut_volume:.3f}",
                        f"{it.fill_volume:.3f}",
                        f"{it.cum_cut:.3f}",
                        f"{it.cum_fill:.3f}",
                    ]
                )
        return str(out)
