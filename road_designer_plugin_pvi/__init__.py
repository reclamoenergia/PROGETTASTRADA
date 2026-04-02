"""QGIS entrypoint for Road Designer Plugin PVI clone."""


def classFactory(iface):
    from .main_plugin import RoadDesignerPlugin

    return RoadDesignerPlugin(iface)
