from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import processing
from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .tin_surface import TinSurface


@dataclass(frozen=True)
class TinBuildParams:
    contour_interval: float
    processing_buffer: float
    simplify_tolerance: float
    axis_signature: str
    raster_source: str


@dataclass
class TinBuildResult:
    surface: TinSurface
    contours_layer: Optional[QgsVectorLayer]
    triangles_layer: Optional[QgsVectorLayer]
    local_extent: QgsRectangle


class TinBuilder:
    def __init__(self):
        self._cache: Dict[TinBuildParams, TinBuildResult] = {}

    def build_from_local_contours(
        self,
        dtm_layer,
        axis_points: List[Tuple[float, float]],
        contour_interval: float,
        processing_buffer: float,
        simplify_tolerance: float = 0.0,
        add_contours_layer: bool = False,
        add_triangles_layer: bool = False,
        use_cache: bool = True,
    ) -> TinBuildResult:
        if not axis_points:
            raise ValueError("Asse allineato vuoto: impossibile derivare l'estensione locale per il TIN.")
        local_extent = self._local_extent(axis_points, processing_buffer)
        key = TinBuildParams(
            contour_interval=float(contour_interval),
            processing_buffer=float(processing_buffer),
            simplify_tolerance=float(simplify_tolerance),
            axis_signature=self._axis_signature(axis_points),
            raster_source=dtm_layer.source(),
        )
        if use_cache and key in self._cache:
            return self._cache[key]

        clip = processing.run(
            "gdal:cliprasterbyextent",
            {
                "INPUT": dtm_layer,
                "PROJWIN": f"{local_extent.xMinimum()},{local_extent.xMaximum()},{local_extent.yMaximum()},{local_extent.yMinimum()}",
                "NODATA": None,
                "OPTIONS": "",
                "DATA_TYPE": 0,
                "OUTPUT": "TEMPORARY_OUTPUT",
            },
        )["OUTPUT"]

        contours = processing.run(
            "gdal:contour",
            {
                "INPUT": clip,
                "BAND": 1,
                "INTERVAL": contour_interval,
                "FIELD_NAME": "elev",
                "CREATE_3D": False,
                "IGNORE_NODATA": True,
                "NODATA": None,
                "OFFSET": 0.0,
                "OUTPUT": "TEMPORARY_OUTPUT",
            },
        )["OUTPUT"]

        if simplify_tolerance > 0:
            contours = processing.run(
                "native:simplifygeometries",
                {
                    "INPUT": contours,
                    "METHOD": 0,
                    "TOLERANCE": simplify_tolerance,
                    "OUTPUT": "TEMPORARY_OUTPUT",
                },
            )["OUTPUT"]

        contour_count = contours.featureCount()
        if contour_count <= 0:
            raise ValueError("Nessuna curva di livello estratta dall'area locale. Aumentare buffer o verificare il DTM.")

        vertices, points_layer = self._vertices_from_contours(contours)
        if len(vertices) < 3:
            raise ValueError("Punti altimetrici insufficienti per triangolare il TIN locale.")

        tri_raw = processing.run(
            "native:delaunaytriangulation",
            {
                "INPUT": points_layer,
                "TOLERANCE": 0.0,
                "OUTPUT": "TEMPORARY_OUTPUT",
            },
        )["OUTPUT"]
        if tri_raw.featureCount() <= 0:
            raise ValueError("Triangolazione Delaunay fallita: nessun triangolo prodotto.")

        triangle_indices, diag_triangles = self._triangles_with_z(tri_raw, vertices)
        surface = TinSurface(vertices=vertices, triangles=triangle_indices)
        if not surface.is_valid():
            raise ValueError("TIN non valido dopo triangolazione.")

        contours_out = contours if add_contours_layer else None
        triangles_out = diag_triangles if add_triangles_layer else None

        if add_contours_layer and contours_out:
            contours_out.setName("TIN_LocalContours")
            QgsProject.instance().addMapLayer(contours_out)
        if add_triangles_layer and triangles_out:
            triangles_out.setName("TIN_Triangles")
            QgsProject.instance().addMapLayer(triangles_out)

        result = TinBuildResult(surface=surface, contours_layer=contours_out, triangles_layer=triangles_out, local_extent=local_extent)
        if use_cache:
            self._cache[key] = result
        return result

    def _local_extent(self, axis_points: Iterable[Tuple[float, float]], buffer_m: float) -> QgsRectangle:
        xs = [p[0] for p in axis_points]
        ys = [p[1] for p in axis_points]
        if not xs or not ys:
            raise ValueError("Impossibile calcolare estensione locale: asse vuoto.")
        rect = QgsRectangle(min(xs), min(ys), max(xs), max(ys))
        if rect.width() <= 0 and rect.height() <= 0:
            raise ValueError("Estensione asse non valida per il processing locale TIN.")
        rect.grow(max(1.0, buffer_m))
        return rect

    def _vertices_from_contours(self, contour_layer: QgsVectorLayer) -> Tuple[List[Tuple[float, float, float]], QgsVectorLayer]:
        field_idx = contour_layer.fields().indexFromName("elev")
        if field_idx < 0:
            raise ValueError("Campo elev non trovato nelle curve di livello estratte.")

        sink = QgsVectorLayer(f"Point?crs={contour_layer.crs().authid()}", "tin_points", "memory")
        prov = sink.dataProvider()
        vertices: List[Tuple[float, float, float]] = []
        seen = set()
        feats = []
        for f in contour_layer.getFeatures():
            geom = f.geometry()
            if geom.isEmpty():
                continue
            z = float(f[field_idx])
            parts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
            for part in parts:
                for pt in part:
                    key = (round(pt.x(), 3), round(pt.y(), 3), round(z, 3))
                    if key in seen:
                        continue
                    seen.add(key)
                    vertices.append((pt.x(), pt.y(), z))
                    pf = QgsFeature()
                    pf.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pt.x(), pt.y())))
                    feats.append(pf)
        prov.addFeatures(feats)
        sink.updateExtents()
        return vertices, sink

    def _triangles_with_z(self, triangle_layer: QgsVectorLayer, vertices: List[Tuple[float, float, float]]):
        vertex_lookup = {(round(x, 3), round(y, 3)): i for i, (x, y, _) in enumerate(vertices)}
        triangle_indices: List[Tuple[int, int, int]] = []
        diag = QgsVectorLayer(f"Polygon?crs={triangle_layer.crs().authid()}", "tin_triangles", "memory")
        dprov = diag.dataProvider()
        dfeats = []
        for f in triangle_layer.getFeatures(QgsFeatureRequest()):
            g = f.geometry()
            if g.isEmpty():
                continue
            poly = g.asPolygon()
            if not poly or len(poly[0]) < 4:
                continue
            ring = poly[0][:3]
            idxs = []
            z_pts = []
            for p in ring:
                idx = vertex_lookup.get((round(p.x(), 3), round(p.y(), 3)))
                if idx is None:
                    break
                idxs.append(idx)
                x, y, z = vertices[idx]
                z_pts.append(QgsPointXY(x, y))
            if len(idxs) != 3 or len(set(idxs)) < 3:
                continue
            triangle_indices.append((idxs[0], idxs[1], idxs[2]))
            df = QgsFeature()
            df.setGeometry(QgsGeometry.fromPolygonXY([[z_pts[0], z_pts[1], z_pts[2], z_pts[0]]]))
            dfeats.append(df)
        dprov.addFeatures(dfeats)
        diag.updateExtents()
        return triangle_indices, diag

    def _axis_signature(self, axis_points: Iterable[Tuple[float, float]]) -> str:
        payload = ";".join(f"{x:.3f},{y:.3f}" for x, y in axis_points)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()
