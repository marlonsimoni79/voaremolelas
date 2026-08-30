"""Central configuration for the voaremolelas app."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # Target location: Almargem, Portugal
    almargem_lat: float = 38.8228
    almargem_lon: float = -9.2594
    timezone: str = "Europe/Lisbon"

    # Windguru live station nearest to Almargem (XPTO, Algueirao, Sintra)
    windguru_base: str = "https://www.windguru.cz"
    windguru_page: str = "https://www.windguru.cz/map/pt/almargem/"
    windguru_api: str = "https://www.windguru.cz/int/iapi.php"
    station_id: int = 3843
    station_name: str = "XPTO (Algueirao, Sintra)"

    # IPMA tephigram (radiosonde) page
    ipma_page: str = "https://www.ipma.pt/pt/otempo/obs.sondagens/"
    ipma_base: str = "https://www.ipma.pt/resources.www/transf/sondagem/"
    ipma_station: str = "LISBOA"

    # Open-Meteo rain data
    openmeteo_url: str = "https://api.open-meteo.com/v1/forecast"

    # Allmetsat METAR/TAF page (LPST = Sintra-Cascais, nearest METAR to Almargem)
    allmetsat_url: str = "https://pt.allmetsat.com/metar-taf/portugal-espanha.php?icao={icao}"
    allmetsat_icao: str = "LPST"
    # Maximum age (seconds) before a METAR is considered stale and the
    # Wunderground PWS fallback is used.
    metar_max_age_seconds: int = 3600

    # Wunderground PWS fallback (fresh local observation for Almargem)
    wunderground_api: str = "https://api.weather.com"
    wunderground_api_key: str = "53b89abc03d14d7ab89abc03d1dd7ab6"
    wunderground_station_id: str = "IPEROP1"
    wunderground_page: str = "https://www.wunderground.com/dashboard/pws/IPEROP1?cm_ven=localwx_pwsdash"
    # Selectable PWS stations: (station_id, display label)
    wunderground_stations: tuple = (("IPEROP1", "IPEROP1"), ("IALMAR8", "IALMAR8"))

    # Flying criteria
    wind_min_kmh: float = 15.0
    wind_max_kmh: float = 22.0
    wind_max_min_kmh: float = 15.0
    wind_max_max_kmh: float = 25.0
    wind_dir_min: float = 270.0  # W (exclusive)
    wind_dir_max: float = 337.5  # NW (inclusive)
    rain_probability_threshold: int = 40  # percent

    # Runtime
    request_timeout: int = 30
    cache_ttl: int = 300  # seconds


config = Config()
