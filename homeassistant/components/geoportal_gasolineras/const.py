"""Constants for the Spain fuel prices (Geoportal Gasolineras) integration."""

from datetime import timedelta

DOMAIN = "geoportal_gasolineras"

SUBENTRY_TYPE_STATION = "station"
SUBENTRY_TYPE_ZONE = "zone"

CONF_PROVINCE_ID = "province_id"
CONF_MUNICIPALITY_ID = "municipality_id"
CONF_STATION_ID = "station_id"
CONF_FUEL = "fuel"
CONF_RADIUS = "radius"
CONF_SHOW_ON_MAP = "show_on_map"

# Prices are published every 30 minutes
SCAN_INTERVAL = timedelta(minutes=30)

ATTRIBUTION = "Data provided by the Spanish Ministry (Geoportal Gasolineras)"
CONFIGURATION_URL = "https://geoportalgasolineras.es/"
