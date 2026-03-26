"""QGIS entrypoint for Road Designer Plugin."""


def classFactory(iface):
    from .main_plugin import RoadDesignerPlugin

    return RoadDesignerPlugin(iface)
