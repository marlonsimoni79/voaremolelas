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

    # Flying criteria
    wind_min_kmh: float = 15.0
    wind_max_kmh: float = 22.0
    wind_dir_min: int = 270  # W
    wind_dir_max: int = 315  # NW
    rain_probability_threshold: int = 40  # percent

    # Runtime
    request_timeout: int = 30
    cache_ttl: int = 300  # seconds


config = Config()
