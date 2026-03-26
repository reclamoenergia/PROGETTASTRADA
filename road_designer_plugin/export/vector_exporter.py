from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

from ..core.alignment import Alignment
from ..core.models import SectionData


class VectorExporter:
    def export_outputs(
        self,
        alignment: Alignment,
        sections: List[SectionData],
        output_folder: str,
        project_name: str,
        crs_authid: str,
    ) -> dict:
        axis_layer = self._build_axis_layer(alignment, crs_authid, f"{project_name}_axis")
        sections_layer = self._build_sections_layer(sections, crs_authid, f"{project_name}_sections")
        slopes_layer = self._build_slopes_layer(sections, crs_authid, f"{project_name}_slopes")

        project = QgsProject.instance()
        project.addMapLayer(axis_layer)
        project.addMapLayer(sections_layer)
        project.addMapLayer(slopes_layer)

        saved_paths: List[str] = []
        if output_folder:
            saved_paths.extend(
                [
                    self._save_layer(axis_layer, output_folder, f"{project_name}_axis"),
                    self._save_layer(sections_layer, output_folder, f"{project_name}_sections"),
                    self._save_layer(slopes_layer, output_folder, f"{project_name}_slopes"),
                ]
            )

        return {
            "axis_layer_name": axis_layer.name(),
            "sections_layer_name": sections_layer.name(),
            "slopes_layer_name": slopes_layer.name(),
            "saved_paths": [p for p in saved_paths if p],
        }

    def _build_axis_layer(self, alignment: Alignment, crs_authid: str, name: str) -> QgsVectorLayer:
        layer = QgsVectorLayer(f"LineString?crs={crs_authid}", name, "memory")
        pr = layer.dataProvider()
        fields = QgsFields()
        fields.append(QgsField("id", QVariant.Int))
        fields.append(QgsField("length_m", QVariant.Double, "double", 18, 3))
        fields.append(QgsField("sample_count", QVariant.Int))
        pr.addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in alignment.points]))
        feat.setAttributes([1, alignment.length, len(alignment.points)])
        pr.addFeature(feat)
        layer.updateExtents()
        return layer

    def _build_sections_layer(self, sections: List[SectionData], crs_authid: str, name: str) -> QgsVectorLayer:
        layer = QgsVectorLayer(f"LineString?crs={crs_authid}", name, "memory")
        pr = layer.dataProvider()
        fields = QgsFields()
        fields.append(QgsField("section_id", QVariant.Int))
        fields.append(QgsField("progressive", QVariant.Double, "double", 18, 3))
        fields.append(QgsField("width_left", QVariant.Double, "double", 18, 3))
        fields.append(QgsField("width_right", QVariant.Double, "double", 18, 3))
        fields.append(QgsField("total_width", QVariant.Double, "double", 18, 3))
        fields.append(QgsField("area_cut", QVariant.Double, "double", 18, 3))
        fields.append(QgsField("area_fill", QVariant.Double, "double", 18, 3))
        fields.append(QgsField("approx_flg", QVariant.Int))
        fields.append(QgsField("note", QVariant.String, "string", 254))
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

    def _build_slopes_layer(self, sections: List[SectionData], crs_authid: str, name: str) -> QgsVectorLayer:
        layer = QgsVectorLayer(f"LineString?crs={crs_authid}", name, "memory")
        pr = layer.dataProvider()
        fields = QgsFields()
        fields.append(QgsField("section_id", QVariant.Int))
        fields.append(QgsField("side", QVariant.String, "string", 8))
        fields.append(QgsField("approx_flg", QVariant.Int))
        fields.append(QgsField("note", QVariant.String, "string", 254))
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

    def _save_layer(self, layer: QgsVectorLayer, folder: str, base_name: str) -> str:
        out_dir = Path(folder)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{base_name}.shp"
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "ESRI Shapefile"
        options.fileEncoding = "UTF-8"
        result, error_message = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer,
            str(path),
            QgsProject.instance().transformContext(),
            options,
        )
        if result != QgsVectorFileWriter.NoError:
            gpkg_path = out_dir / f"{base_name}.gpkg"
            options.driverName = "GPKG"
            options.layerName = base_name
            result, error_message = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer,
                str(gpkg_path),
                QgsProject.instance().transformContext(),
                options,
            )
            if result != QgsVectorFileWriter.NoError:
                raise RuntimeError(f"Esportazione vettoriale fallita per '{base_name}': {error_message}")
            return str(gpkg_path)
        return str(path)
