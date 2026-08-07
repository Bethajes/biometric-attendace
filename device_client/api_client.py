import requests


class DjangoApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/') + '/'

    def _json_or_empty(self, response):
        if response.headers.get('content-type', '').startswith('application/json'):
            return response.json()
        return {}

    def post(self, path: str, data=None, timeout=5):
        url = f"{self.base_url}{path.lstrip('/') }"
        response = requests.post(url, json=data or {}, timeout=timeout)
        return response.status_code, self._json_or_empty(response)

    def get(self, path: str, timeout=5):
        url = f"{self.base_url}{path.lstrip('/') }"
        response = requests.get(url, timeout=timeout)
        return response.status_code, self._json_or_empty(response)
