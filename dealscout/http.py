"""HTTP-Client mit Drosselung und Wiederholungen – wir wollen die Börsen nicht belasten."""

from __future__ import annotations

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36 dealscout/0.1 (private Nutzung)"
)


class PoliteSession:
    """requests-Session, die zwischen zwei Anfragen mindestens `delay` Sekunden wartet."""

    def __init__(self, delay: float = 1.5, timeout: float = 30.0):
        self.delay = delay
        self.timeout = timeout
        self._last = 0.0
        self.s = requests.Session()
        self.s.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "de-DE,de;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        retry = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        self.s.mount("https://", HTTPAdapter(max_retries=retry))
        self.s.mount("http://", HTTPAdapter(max_retries=retry))

    def get(self, url: str, params: dict | list | None = None) -> str:
        return self._request("GET", url, params=params)

    def post(self, url: str, data: dict) -> str:
        return self._request("POST", url, data=data)

    def _request(self, method: str, url: str, **kw) -> str:
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        log.debug("%s %s %s", method, url, kw.get("params") or kw.get("data") or "")
        resp = self.s.request(method, url, timeout=self.timeout, **kw)
        self._last = time.monotonic()
        resp.raise_for_status()
        # Manche Server (z.B. DUB) senden kein Charset -> requests rät ISO-8859-1.
        if "charset" not in resp.headers.get("Content-Type", "").lower():
            resp.encoding = "utf-8"
        return resp.text
