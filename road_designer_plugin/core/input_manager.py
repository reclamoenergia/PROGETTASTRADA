from __future__ import annotations

from typing import Optional, Tuple

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsMapLayer,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsWkbTypes,
    Qgis,
)


class InputManager:
    def __init__(self, iface):
        self.iface = iface

    def layer_by_name(self, name: str) -> Optional[QgsMapLayer]:
        if not name:
            return None
        layers = QgsProject.instance().mapLayersByName(name)
        return layers[0] if layers else None

    def validate(
        self,
        dtm: QgsRasterLayer,
        axis: QgsVectorLayer,
        polygon: QgsVectorLayer,
        forced: Optional[QgsVectorLayer] = None,
    ) -> Tuple[bool, str]:
        if not dtm or not axis or not polygon:
            return False, "Selezionare DTM, asse e poligono di viabilità."
        if dtm.type() != QgsMapLayer.RasterLayer:
            return False, "Il layer DTM deve essere raster."
        if QgsWkbTypes.geometryType(axis.wkbType()) != QgsWkbTypes.LineGeometry:
            return False, "Il layer asse deve essere lineare."
        if QgsWkbTypes.geometryType(polygon.wkbType()) != QgsWkbTypes.PolygonGeometry:
            return False, "Il layer viabilità deve essere poligonale."
        if forced and QgsWkbTypes.geometryType(forced.wkbType()) != QgsWkbTypes.PointGeometry:
            return False, "Il layer quote imposte deve essere puntuale."
        crs_ok, msg = self._check_crs(dtm.crs(), axis.crs(), polygon.crs(), forced.crs() if forced else None)
        if not crs_ok:
            return False, msg
        if forced and forced.fields().indexFromName("z") < 0:
            self.iface.messageBar().pushMessage(
                "Road Designer",
                "Layer quote imposte senza campo 'z': verrà ignorato.",
                level=Qgis.Warning,
                duration=5,
            )
        return True, "OK"

    def _check_crs(
        self,
        dtm_crs: QgsCoordinateReferenceSystem,
        axis_crs: QgsCoordinateReferenceSystem,
        poly_crs: QgsCoordinateReferenceSystem,
        forced_crs: Optional[QgsCoordinateReferenceSystem],
    ) -> Tuple[bool, str]:
        refs = [dtm_crs.authid(), axis_crs.authid(), poly_crs.authid()]
        if forced_crs:
            refs.append(forced_crs.authid())
        if len(set(refs)) > 1:
            return False, "I layer hanno CRS differenti. Uniformare i CRS prima del calcolo."
        return True, "OK"
