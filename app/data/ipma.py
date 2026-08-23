"""Fetch tephigram (radiosonde sounding) image URLs from IPMA.

IPMA publishes tephigrams at ``https://www.ipma.pt/pt/otempo/obs.sondagens/``.
The image links are not present as static HTML; they are generated client-side
from JavaScript arrays embedded in the page (``box1Array`` for stations and
``box3Array`` for the per-station file lists).  We scrape those arrays and
rebuild the image URLs.

The markup is unofficial and can change, so all parsing lives here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

from app.config import config

logger = logging.getLogger(__name__)


class IpmmaError(RuntimeError):
    """Raised when the IPMA page cannot be fetched or parsed."""


@dataclass
class Tephigram:
    """A single tephigram image reference."""

    station_code: str
    station_name: str
    kind: str  # "observation" or "forecast"
    label: str  # e.g. "12UTC" or "H+24"
    filename: str
    url: str


def _extract_block(html: str, name: str) -> str:
    """Return the text of a ``name = new Array( ... )`` block."""
    match = re.search(rf"{re.escape(name)}\s*=\s*new Array\(", html)
    if not match:
        raise IpmmaError(f"Could not find {name} in IPMA page")
    start = match.end()
    depth = 1
    index = start
    while index < len(html) and depth > 0:
        char = html[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        index += 1
    return html[start : index - 1]


def parse_tephigrams(html: str, base_url: str, page_url: str) -> List[Tephigram]:
    """Parse the embedded JS arrays into a list of tephigram references."""
    content_match = re.search(r'contentPath\s*=\s*"([^"]+)"', html)
    if not content_match:
        raise IpmmaError("Could not find contentPath in IPMA page")
    content_path = content_match.group(1)
    if not content_path.startswith("http"):
        # contentPath is relative to the page origin.
        origin = page_url.split("/", 3)
        origin = "/".join(origin[:3])
        content_path = origin + content_path
    base = content_path.rstrip("/") + "/"

    # station code -> display name
    stations: Dict[str, str] = {}
    for code, name in re.findall(r'"(\d{5})::([^"]+)"', _extract_block(html, "box1Array")):
        stations[code] = name

    tephigrams: List[Tephigram] = []
    block = _extract_block(html, "box3Array")
    for filename, label in re.findall(r'"(tef_[^"]+\.png)::([^"]+)"', block):
        # Filenames look like tef_LISBOA_08536_0_12_00.png
        # Groups: name, code, kind(0=obs/1=fcst), rest.
        match = re.match(r"tef_(?P<name>.+)_(?P<code>\d{5})_(?P<kind>[01])_(?P<rest>.+)\.png", filename)
        if not match:
            logger.warning("Skipping unrecognised tephigram filename: %s", filename)
            continue
        code = match.group("code")
        kind = "observation" if match.group("kind") == "0" else "forecast"
        tephigrams.append(
            Tephigram(
                station_code=code,
                station_name=stations.get(code, match.group("name")),
                kind=kind,
                label=label,
                filename=filename,
                url=base + filename,
            )
        )

    if not tephigrams:
        raise IpmmaError("No tephigrams found in IPMA page")
    return tephigrams


class IpmmaClient:
    """Client that fetches and parses the IPMA tephigram page."""

    def __init__(
        self,
        page_url: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.page_url = page_url or config.ipma_page
        self.base_url = base_url or config.ipma_base
        self.timeout = timeout or config.request_timeout

    def fetch_tephigrams(self) -> List[Tephigram]:
        resp = requests.get(self.page_url, timeout=self.timeout)
        resp.raise_for_status()
        return parse_tephigrams(resp.text, self.base_url, self.page_url)

    def for_station(self, station_name: str) -> List[Tephigram]:
        """Return tephigrams for a station, matching by display name (case-insensitive)."""
        target = station_name.lower()
        return [
            tephigram
            for tephigram in self.fetch_tephigrams()
            if tephigram.station_name.lower() == target
        ]


def fetch_tephigrams() -> List[Tephigram]:
    """Convenience wrapper used by the API layer."""
    return IpmmaClient().fetch_tephigrams()
