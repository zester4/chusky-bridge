import base64
import ipaddress
import socket
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from chusky_bridge.config import settings
from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.files import FileNotApproved, resolve_approved_file

METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


def assert_public_host(host: str, allow_private: bool) -> None:
    """Block SSRF targets: private, loopback, link-local, and reserved addresses."""
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ConnectorError("upstream host could not be resolved") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ConnectorError("upstream host resolves to a non-public address")


def encode_segment(value: Any) -> str:
    text = str(value)
    if not text or text in {".", ".."}:
        raise ConnectorError("invalid path segment")
    return quote(text, safe="")


def auth_headers(config: dict[str, Any]) -> dict[str, str]:
    secret = config.get("api_key")
    if not secret:
        return {}
    scheme = config.get("auth_scheme", "bearer")
    if scheme == "bearer":
        return {"Authorization": f"Bearer {secret}"}
    if scheme == "basic":
        token = base64.b64encode(f"{config.get('username', '')}:{secret}".encode()).decode()
        return {"Authorization": f"Basic {token}"}
    if scheme == "header":
        return {config.get("auth_header", "X-API-Key"): secret}
    raise ConnectorError("unsupported auth_scheme")


def _tls_material(config: dict[str, Any]) -> tuple[tuple[str, str] | None, str | bool]:
    """Resolve mTLS client certificate and CA bundle from the approved certificate directory."""
    cert = key = None
    try:
        if config.get("client_cert_path") or config.get("client_key_path"):
            if not (config.get("client_cert_path") and config.get("client_key_path")):
                raise ConnectorError("client_cert_path and client_key_path must be set together")
            cert = str(resolve_approved_file(config["client_cert_path"], settings.cert_dir))
            key = str(resolve_approved_file(config["client_key_path"], settings.cert_dir))
        verify: str | bool = True
        if config.get("ca_bundle_path"):
            verify = str(resolve_approved_file(config["ca_bundle_path"], settings.cert_dir))
    except FileNotApproved as exc:
        raise ConnectorError(f"TLS material: {exc}") from exc
    return ((cert, key) if cert and key else None), verify


class HttpOrigin:
    """One pinned HTTPS origin. Callers supply paths only, never hosts or full URLs."""

    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str],
        allow_private_network: bool = False,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = 100_000,
        client_cert: tuple[str, str] | None = None,
        verify: str | bool = True,
    ):
        base = urlsplit(base_url)
        if base.scheme != "https" or not base.hostname:
            raise ConnectorError("base_url must be an absolute https URL")
        self._origin = f"https://{base.netloc}"
        self._base_path = base.path.rstrip("/")
        self._host = base.hostname
        self._headers = {"User-Agent": "ChuskyBridge/1.0", **headers}
        self._allow_private = allow_private_network
        self._timeout = timeout_seconds
        self._max_bytes = max_response_bytes
        self._cert = client_cert
        self._verify = verify

    @classmethod
    def from_config(cls, config: dict[str, Any], *, extra_headers: dict[str, str] | None = None) -> "HttpOrigin":
        cert, verify = _tls_material(config)
        return cls(
            config["base_url"],
            headers={**auth_headers(config), **(extra_headers or {})},
            allow_private_network=bool(config.get("allow_private_network", False)),
            timeout_seconds=float(config.get("timeout_seconds", 10)),
            max_response_bytes=int(config.get("max_response_bytes", 100_000)),
            client_cert=cert,
            verify=verify,
        )

    def url(self, path: str) -> str:
        return f"{self._origin}{self._base_path}{path}"

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> tuple[int, str, bytes]:
        method = method.upper()
        if method not in METHODS:
            raise ConnectorError("HTTP method not allowed")
        assert_public_host(self._host, self._allow_private)

        try:
            with (
                httpx.Client(
                    timeout=self._timeout,
                    follow_redirects=False,
                    cert=self._cert,
                    verify=self._verify,
                ) as client,
                client.stream(
                    method,
                    self.url(path),
                    params=params if method == "GET" else None,
                    json=None if method == "GET" else json_body,
                    headers=self._headers,
                ) as response,
            ):
                status = response.status_code
                content_type = response.headers.get("content-type", "")
                if status >= 300:
                    raise ConnectorError(f"upstream returned HTTP {status}")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > self._max_bytes:
                        raise ConnectorError("upstream response exceeded size limit")
                    chunks.append(chunk)
        except httpx.HTTPError as exc:
            raise ConnectorError("upstream request failed") from exc
        return status, content_type, b"".join(chunks)
