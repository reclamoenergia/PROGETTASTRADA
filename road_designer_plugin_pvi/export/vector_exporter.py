from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QMetaType

from ..core.alignment import Alignment
from ..core.models import SectionData


class VectorExporter:
    def _field(self, name: str, field_type, type_name: str = "", length: int = 0, precision: int = 0) -> QgsField:
        # QGIS >= 3.40: prefer QMetaType-based constructor to avoid QVariant deprecation warnings.
        return QgsField(name=name, type=field_type, typeName=type_name, len=length, prec=precision)

    def export_outputs(
        self,
        alignment: Alignment,
        sections: List[SectionData],
        output_folder: str,
        project_name: str,
        crs_authid: str,
        surface_sections: List[SectionData] | None = None,
    ) -> dict:
        surface_input = surface_sections if surface_sections is not None else sections
        axis_layer = self._build_axis_layer(alignment, crs_authid, f"{project_name}_axis")
        sections_layer = self._build_sections_layer(sections, crs_authid, f"{project_name}_sections")
        slopes_layer = self._build_slopes_layer(surface_input, crs_authid, f"{project_name}_slopes")
        surface_layer = self._build_project_surface_layer(
            alignment,
            surface_input,
            crs_authid,
            f"{project_name}_project_surface",
            project_name,
        )
        footprint_layer = self._build_footprint_layer(
            alignment,
            surface_input,
            crs_authid,
            f"{project_name}_project_footprint",
            project_name,
        )

        project = QgsProject.instance()
        project.addMapLayer(axis_layer)
        project.addMapLayer(sections_layer)
        project.addMapLayer(slopes_layer)
        project.addMapLayer(surface_layer)
        project.addMapLayer(footprint_layer)

        saved_paths: List[str] = []
        if output_folder:
            saved_paths.extend(
                [
                    self._save_layer(axis_layer, output_folder, f"{project_name}_axis"),
                    self._save_layer(sections_layer, output_folder, f"{project_name}_sections"),
                    self._save_layer(slopes_layer, output_folder, f"{project_name}_slopes"),
                    self._save_layer(surface_layer, output_folder, f"{project_name}_project_surface"),
                    self._save_layer(footprint_layer, output_folder, f"{project_name}_project_footprint"),
                ]
            )

        return {
            "axis_layer_name": axis_layer.name(),
            "sections_layer_name": sections_layer.name(),
            "slopes_layer_name": slopes_layer.name(),
            "surface_layer_name": surface_layer.name(),
            "footprint_layer_name": footprint_layer.name(),
            "saved_paths": [p for p in saved_paths if p],
        }

    def _build_axis_layer(self, alignment: Alignment, crs_authid: str, name: str) -> QgsVectorLayer:
        layer = QgsVectorLayer(f"LineString?crs={crs_authid}", name, "memory")
        pr = layer.dataProvider()
        fields = QgsFields()
        fields.append(self._field("id", QMetaType.Type.Int))
        fields.append(self._field("length_m", QMetaType.Type.Double, "double", 18, 3))
        fields.append(self._field("sample_count", QMetaType.Type.Int))
        pr.addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([self._as_qgspointxy(pt) for pt in alignment.points]))
        feat.setAttributes([1, alignment.length, len(alignment.points)])
        pr.addFeature(feat)
        layer.updateExtents()
        return layer

    def _build_sections_layer(self, sections: List[SectionData], crs_authid: str, name: str) -> QgsVectorLayer:
        layer = QgsVectorLayer(f"LineString?crs={crs_authid}", name, "memory")
        pr = layer.dataProvider()
        fields = QgsFields()
        fields.append(self._field("section_id", QMetaType.Type.Int))
        fields.append(self._field("progressive", QMetaType.Type.Double, "double", 18, 3))
        fields.append(self._field("width_left", QMetaType.Type.Double, "double", 18, 3))
        fields.append(self._field("width_right", QMetaType.Type.Double, "double", 18, 3))
        fields.append(self._field("total_width", QMetaType.Type.Double, "double", 18, 3))
        fields.append(self._field("area_cut", QMetaType.Type.Double, "double", 18, 3))
        fields.append(self._field("area_fill", QMetaType.Type.Double, "double", 18, 3))
        fields.append(self._field("approx_flg", QMetaType.Type.Int))
        fields.append(self._field("note", QMetaType.Type.QString, "string", 254))
        pr.addAttributes(fields)
        layer.updateFields()

        feats: List[QgsFeature] = []
        for sec in sections:
            if not sec.offsets:
                continue
            p1 = self._point_from_offset(sec, sec.offsets[0])
            p2 = self._point_from_offset(sec, sec.offsets[-1])
            wi = sec.width_info
            approx = (not sec.side_slope_left_resolved) or (not sec.side_slope_right_resolved)
            notes = []
            if not sec.side_slope_left_resolved and sec.side_slope_left_note:
                notes.append(f"L: {sec.side_slope_left_note}")
            if not sec.side_slope_right_resolved and sec.side_slope_right_note:
                notes.append(f"R: {sec.side_slope_right_note}")

            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPolylineXY([p1, p2]))
            feat.setAttributes(
                [
                    sec.index,
                    sec.progressive,
                    wi.left_width if wi else 0.0,
                    wi.right_width if wi else 0.0,
                    wi.total_width if wi else 0.0,
                    sec.cut_area,
                    sec.fill_area,
                    1 if approx else 0,
                    " | ".join(notes),
                ]
            )
            feats.append(feat)

        pr.addFeatures(feats)
        layer.updateExtents()
        return layer

    def _build_project_surface_layer(
        self,
        alignment: Alignment,
        sections: List[SectionData],
        crs_authid: str,
        name: str,
        project_name: str,
    ) -> QgsVectorLayer:
        layer = QgsVectorLayer(f"Polygon?crs={crs_authid}", name, "memory")
        pr = layer.dataProvider()
        fields = QgsFields()
        fields.append(self._field("id", QMetaType.Type.Int))
        fields.append(self._field("length_m", QMetaType.Type.Double, "double", 18, 3))
        fields.append(self._field("source_nm", QMetaType.Type.QString, "string", 120))
        fields.append(self._field("note", QMetaType.Type.QString, "string", 254))
        pr.addAttributes(fields)
        layer.updateFields()

        left_pts: List[QgsPointXY] = []
        right_pts: List[QgsPointXY] = []
        approx_sections = 0
        for sec in sections:
            if not sec.offsets:
                continue
            wi = sec.width_info
            left_off = -wi.left_width if wi is not None else (sec.road_core_left_offset if sec.road_core_left_offset is not None else -1.0)
            right_off = wi.right_width if wi is not None else (sec.road_core_right_offset if sec.road_core_right_offset is not None else 1.0)
            if right_off <= left_off:
                continue
            left_pts.append(self._point_from_offset(sec, left_off))
            right_pts.append(self._point_from_offset(sec, right_off))
            if (not sec.side_slope_left_resolved) or (not sec.side_slope_right_resolved):
                approx_sections += 1

        note = ""
        if len(left_pts) >= 2 and len(right_pts) >= 2:
            ring = left_pts + list(reversed(right_pts))
            if ring and (ring[0] != ring[-1]):
                ring.append(ring[0])
            geom = QgsGeometry.fromPolygonXY([ring])
            if geom.isEmpty():
                note = "Poligono superficie vuoto."
            else:
                if not geom.isGeosValid():
                    note = "Geometria superficie riparata con makeValid."
                    geom = geom.makeValid()
                    if geom.wkbType() in (QgsWkbTypes.GeometryCollection, QgsWkbTypes.Unknown):
                        geoms = geom.asGeometryCollection()
                        polys = [g for g in geoms if QgsWkbTypes.geometryType(g.wkbType()) == QgsWkbTypes.PolygonGeometry]
                        if polys:
                            geom = polys[0]
                        else:
                            note = "makeValid non ha prodotto un poligono valido."
                if not geom.isEmpty():
                    feat = QgsFeature(layer.fields())
                    if approx_sections > 0:
                        note = (note + " " if note else "") + f"{approx_sections} sezioni con scarpate approssimate."
                    feat.setGeometry(geom)
                    feat.setAttributes([1, alignment.length, project_name, note])
                    pr.addFeature(feat)
        else:
            note = "Punti insufficienti per costruire la superficie progetto."
        layer.updateExtents()
        return layer

    def _build_footprint_layer(
        self,
        alignment: Alignment,
        sections: List[SectionData],
        crs_authid: str,
        name: str,
        project_name: str,
    ) -> QgsVectorLayer:
        layer = QgsVectorLayer(f"Polygon?crs={crs_authid}", name, "memory")
        pr = layer.dataProvider()
        fields = QgsFields()
        fields.append(self._field("id", QMetaType.Type.Int))
        fields.append(self._field("length_m", QMetaType.Type.Double, "double", 18, 3))
        fields.append(self._field("source_nm", QMetaType.Type.QString, "string", 120))
        fields.append(self._field("note", QMetaType.Type.QString, "string", 254))
        pr.addAttributes(fields)
        layer.updateFields()

        left_pts: List[QgsPointXY] = []
        right_pts: List[QgsPointXY] = []
        approx_sections = 0
        for sec in sections:
            if not sec.offsets:
                continue
            l_off = sec.side_slope_left_outer_offset if sec.side_slope_left_outer_offset is not None else sec.offsets[0]
            r_off = sec.side_slope_right_outer_offset if sec.side_slope_right_outer_offset is not None else sec.offsets[-1]
            if r_off <= l_off:
                continue
            left_pts.append(self._point_from_offset(sec, l_off))
            right_pts.append(self._point_from_offset(sec, r_off))
            if (not sec.side_slope_left_resolved) or (not sec.side_slope_right_resolved):
                approx_sections += 1

        note = ""
        if len(left_pts) >= 2 and len(right_pts) >= 2:
            ring = left_pts + list(reversed(right_pts))
            if ring and (ring[0] != ring[-1]):
                ring.append(ring[0])
            geom = QgsGeometry.fromPolygonXY([ring])
            if geom.isEmpty():
                note = "Poligono footprint vuoto."
            else:
                if not geom.isGeosValid():
                    note = "Geometria footprint riparata con makeValid."
                    geom = geom.makeValid()
                    if QgsWkbTypes.geometryType(geom.wkbType()) != QgsWkbTypes.PolygonGeometry:
                        geoms = geom.asGeometryCollection()
                        polys = [g for g in geoms if QgsWkbTypes.geometryType(g.wkbType()) == QgsWkbTypes.PolygonGeometry]
                        if polys:
                            geom = polys[0]
                        else:
                            note = "makeValid non ha prodotto un poligono footprint valido."
                if not geom.isEmpty():
                    feat = QgsFeature(layer.fields())
                    if approx_sections > 0:
                        note = (note + " " if note else "") + f"{approx_sections} sezioni con scarpate approssimate."
                    feat.setGeometry(geom)
                    feat.setAttributes([1, alignment.length, project_name, note])
                    pr.addFeature(feat)
        else:
            note = "Punti insufficienti per costruire il footprint dell'opera."
        layer.updateExtents()
        return layer

    def _build_slopes_layer(self, sections: List[SectionData], crs_authid: str, name: str) -> QgsVectorLayer:
        layer = QgsVectorLayer(f"LineString?crs={crs_authid}", name, "memory")
        pr = layer.dataProvider()
        fields = QgsFields()
        fields.append(self._field("section_id", QMetaType.Type.Int))
        fields.append(self._field("side", QMetaType.Type.QString, "string", 8))
        fields.append(self._field("approx_flg", QMetaType.Type.Int))
        fields.append(self._field("note", QMetaType.Type.QString, "string", 254))
        pr.addAttributes(fields)
        layer.updateFields()

        left_pts: List[Tuple[SectionData, QgsPointXY]] = []
        right_pts: List[Tuple[SectionData, QgsPointXY]] = []
        for sec in sections:
            l_off = sec.side_slope_left_outer_offset if sec.side_slope_left_outer_offset is not None else (sec.offsets[0] if sec.offsets else 0.0)
            r_off = sec.side_slope_right_outer_offset if sec.side_slope_right_outer_offset is not None else (sec.offsets[-1] if sec.offsets else 0.0)
            left_pts.append((sec, self._point_from_offset(sec, l_off)))
            right_pts.append((sec, self._point_from_offset(sec, r_off)))

        feats: List[QgsFeature] = []
        for sec, pt in left_pts:
            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(sec.axis_point[0], sec.axis_point[1]), pt]))
            feat.setAttributes([sec.index, "left", 0 if sec.side_slope_left_resolved else 1, sec.side_slope_left_note])
            feats.append(feat)

        for sec, pt in right_pts:
            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(sec.axis_point[0], sec.axis_point[1]), pt]))
            feat.setAttributes([sec.index, "right", 0 if sec.side_slope_right_resolved else 1, sec.side_slope_right_note])
            feats.append(feat)

        if len(left_pts) >= 2:
            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPolylineXY([pt for _, pt in left_pts]))
            feat.setAttributes([-1, "left", 0, "Breakline longitudinale sinistra"])
            feats.append(feat)
        if len(right_pts) >= 2:
            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPolylineXY([pt for _, pt in right_pts]))
            feat.setAttributes([-1, "right", 0, "Breakline longitudinale destra"])
            feats.append(feat)

        pr.addFeatures(feats)
        layer.updateExtents()
        return layer

    def _point_from_offset(self, sec: SectionData, offset: float) -> QgsPointXY:
        return QgsPointXY(sec.axis_point[0] + sec.normal[0] * offset, sec.axis_point[1] + sec.normal[1] * offset)

    def _as_qgspointxy(self, point: Sequence[float] | QgsPointXY) -> QgsPointXY:
        if isinstance(point, QgsPointXY):
            return point
        if hasattr(point, "x") and hasattr(point, "y"):
            return QgsPointXY(float(point.x()), float(point.y()))
        if len(point) < 2:
            raise ValueError("Punto non valido per esportazione asse.")
        return QgsPointXY(float(point[0]), float(point[1]))

    def _extract_writer_result(self, result_obj) -> tuple[int, str]:
        if isinstance(result_obj, tuple):
            if len(result_obj) >= 2:
                return int(result_obj[0]), str(result_obj[1] or "")
            if len(result_obj) == 1:
                return int(result_obj[0]), ""
        return int(result_obj), ""

    def _save_layer(self, layer: QgsVectorLayer, folder: str, base_name: str) -> str:
        out_dir = Path(folder)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{base_name}.shp"
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "ESRI Shapefile"
        options.fileEncoding = "UTF-8"
        write_result = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer,
            str(path),
            QgsProject.instance().transformContext(),
            options,
        )
        result, error_message = self._extract_writer_result(write_result)
        if result != QgsVectorFileWriter.NoError:
            gpkg_path = out_dir / f"{base_name}.gpkg"
            options.driverName = "GPKG"
            options.layerName = base_name
            write_result = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer,
                str(gpkg_path),
                QgsProject.instance().transformContext(),
                options,
            )
            result, error_message = self._extract_writer_result(write_result)
            if result != QgsVectorFileWriter.NoError:
                raise RuntimeError(f"Esportazione vettoriale fallita per '{base_name}': {error_message}")
            return str(gpkg_path)
        return str(path)
