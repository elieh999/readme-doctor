from __future__ import annotations

import ipaddress
import socket
import ssl
from urllib.parse import urlsplit, urlunsplit

import httpx

from readme_doctor.checks.base import CheckContext
from readme_doctor.models import Confidence, Finding

USER_AGENT = "README-Doctor/0.1 (+https://github.com/elieh999/readme-doctor)"
# Statuses that mean the site declined to answer rather than that the link is broken. Reporting
# them as broken links would make results depend on unrelated site behavior.
TRANSIENT_STATUSES = {408, 425, 429, 999}


class UnsafeRemoteURL(Exception):
    pass


def redact_url(url: str) -> str:
    """Remove any credentials embedded in a URL before it appears in a report."""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if parsed.port:
        host += f":{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))


def _ignored(hostname: str | None, ignored_domains: list[str]) -> bool:
    """Match a host against configured domains, including its subdomains."""
    if not hostname:
        return False
    host = hostname.casefold()
    for domain in ignored_domains:
        pattern = domain.casefold().lstrip(".")
        if host == pattern or host.endswith(f".{pattern}"):
            return True
    return False


def _obviously_private(hostname: str | None) -> bool:
    if not hostname:
        return True
    host = hostname.casefold().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        return False


def _require_public_destination(request: httpx.Request) -> None:
    hostname = request.url.host
    if _obviously_private(hostname):
        raise UnsafeRemoteURL("private network destination blocked")
    try:
        addresses = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(hostname, request.url.port)
        }
    except (OSError, ValueError) as exc:
        raise httpx.ConnectError("hostname resolution failed", request=request) from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise UnsafeRemoteURL("private network destination blocked")


def _describe(error: Exception) -> str:
    if isinstance(error, httpx.ConnectTimeout | httpx.ReadTimeout | httpx.PoolTimeout):
        return "timeout"
    if isinstance(error, httpx.TooManyRedirects):
        return "too many redirects"
    if isinstance(error.__cause__, ssl.SSLError) or isinstance(error, httpx.ConnectError):
        cause = error.__cause__
        if isinstance(cause, ssl.SSLCertVerificationError):
            return "certificate verification failed"
        return "connection failed"
    return type(error).__name__


def check_remote_links(context: CheckContext) -> list[Finding]:
    settings = context.config.rules.remote_links
    if not settings.enabled:
        return []
    findings: list[Finding] = []
    # One result per URL for the whole run, so a link repeated in the README is requested once.
    cache: dict[str, tuple[int | None, str | None]] = {}
    with httpx.Client(
        timeout=settings.timeout_seconds,
        follow_redirects=True,
        max_redirects=settings.redirect_limit,
        headers={"User-Agent": USER_AGENT},
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        transport=httpx.HTTPTransport(retries=settings.retries),
        event_hooks={"request": [_require_public_destination]},
    ) as client:
        for link in context.document.links:
            url = link.destination
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"}:
                continue
            if _ignored(parsed.hostname, settings.ignored_domains):
                continue
            if url not in cache:
                if _obviously_private(parsed.hostname):
                    cache[url] = (None, "private network destination blocked")
                else:
                    try:
                        # Never transmit credentials copied from README text. The sanitized URL is
                        # also used for redirects, where the request hook validates every target.
                        request_url = redact_url(url)
                        response = client.head(request_url)
                        if response.status_code in {403, 405, 501}:
                            # These mean the host refused the method rather than that the target is
                            # missing, so confirm with GET. A 404 from HEAD is taken at face value
                            # to avoid a second request for every broken link.
                            response = client.get(request_url)
                        cache[url] = (response.status_code, None)
                    except UnsafeRemoteURL as exc:
                        cache[url] = (None, str(exc))
                    except httpx.HTTPError as exc:
                        cache[url] = (None, _describe(exc))
            status, error = cache[url]
            if status in TRANSIENT_STATUSES or (status is not None and 500 <= status < 600):
                continue
            if error is None and (status is None or status in settings.allowed_status_codes):
                continue
            finding = context.finding(
                "RD017",
                f"Remote link could not be validated: {redact_url(url)}",
                line=link.line,
                evidence=f"status={status if status is not None else error}",
                confidence=Confidence.MEDIUM if error else Confidence.HIGH,
            )
            if finding:
                findings.append(finding)
    return findings
