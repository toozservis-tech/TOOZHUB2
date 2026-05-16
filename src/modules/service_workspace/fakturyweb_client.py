import json
import urllib.parse
from typing import Any, Dict, Optional
import httpx

class FakturyWebError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None, payload: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status = status
        self.payload = payload or {}

def build_fakturyweb_url(endpoint: str, payload: dict) -> str:
    encoded_json = urllib.parse.quote(json.dumps(payload, ensure_ascii=False))
    return f"{endpoint}?data={encoded_json}"

class FakturyWebTestClient:
    def __init__(self, api_key: str, email: str, base_url: str = "https://www.fakturyweb.cz/"):
        self.api_key = api_key
        self.email = email
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=10.0)

    def call_fakturyweb(self, endpoint: str, payload: dict, requires_session: bool = False) -> dict:
        if requires_session:
            init_payload = {"key": self.api_key, "email": self.email}
            init_url = build_fakturyweb_url(f"{self.base_url}/api/init", init_payload)
            init_resp = self.client.get(init_url)
            init_resp.raise_for_status()
            try:
                init_data = init_resp.json()
                if init_data.get("status") != 1:
                    raise FakturyWebError(f"FakturyWeb init vrátil chybu status={init_data.get('status')}", status=init_data.get("status"), payload=init_data)
            except ValueError:
                raise FakturyWebError("FakturyWeb init vrátil neplatnou JSON odpověď.")

        url = build_fakturyweb_url(f"{self.base_url}/{endpoint.lstrip('/')}", payload)
        resp = self.client.get(url)
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            raise FakturyWebError("FakturyWeb vrátil neplatnou JSON odpověď.")
        
        status = data.get("status")
        if status != 1:
            raise FakturyWebError(f"FakturyWeb vrátil chybu č. {status}", status=status, payload=data)
        
        return data

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
