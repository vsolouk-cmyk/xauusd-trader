from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


class TwelveDataError(RuntimeError):
    """Raised when Twelve Data API returns an unexpected response."""


@dataclass(frozen=True)
class TwelveDataConfig:
    base_url: str = "https://api.twelvedata.com"


class TwelveDataClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_sec: int = 30,
        max_retries: int = 3,
        retry_sleep_sec: float = 2.0,
    ) -> None:
        self.api_key = api_key or os.getenv("TWELVEDATA_API_KEY", "").strip()
        if not self.api_key:
            raise TwelveDataError("Missing TWELVEDATA_API_KEY environment variable.")

        self.config = TwelveDataConfig()
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.retry_sleep_sec = retry_sleep_sec
        self.session = requests.Session()

    def get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.config.base_url}/{endpoint.lstrip('/')}"
        request_params = {k: v for k, v in dict(params).items() if v is not None}
        request_params["apikey"] = self.api_key

        last_error: Optional[BaseException] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, params=request_params, timeout=self.timeout_sec)

                if response.status_code == 200:
                    payload = response.json()
                    if str(payload.get("status", "")).lower() == "error":
                        raise TwelveDataError(
                            "Twelve Data API error: "
                            f"code={payload.get('code')}, message={payload.get('message')}"
                        )
                    return payload

                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    time.sleep(self.retry_sleep_sec * attempt)
                    continue

                raise TwelveDataError(
                    f"Twelve Data GET failed: status={response.status_code}, "
                    f"url={response.url}, body={response.text[:500]}"
                )

            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_sleep_sec * attempt)
                    continue
                raise TwelveDataError(f"Twelve Data request failed after retries: {exc}") from exc

        raise TwelveDataError(f"Twelve Data request failed: {last_error}")

    def time_series(
        self,
        symbol: str,
        interval: str,
        outputsize: int = 500,
        timezone: str = "UTC",
        order: str = "ASC",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        if outputsize < 1:
            raise ValueError("outputsize must be positive.")

        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": int(outputsize),
            "timezone": timezone,
            "order": order,
            "format": "JSON",
            "start_date": start_date,
            "end_date": end_date,
        }
        return self.get("time_series", params=params)
