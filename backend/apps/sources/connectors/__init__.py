from .indicators import (IMFDataMapperConnector, ManualDatasetConnector, RSFIndexConnector, TransparencyCPIConnector,
                         UNDPHDRConnector, WorldBankConnector)
from .news import RSSConnector

REGISTRY = {c.key: c for c in [WorldBankConnector, TransparencyCPIConnector, IMFDataMapperConnector, UNDPHDRConnector,
                                RSFIndexConnector, ManualDatasetConnector, RSSConnector]}


def get_connector(source):
    cls = REGISTRY.get(source.connector)
    return cls(source) if cls else None
