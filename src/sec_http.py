"""Shared SEC request policy for sequential, single-process CLI runs."""
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests


class SecAccessError(requests.HTTPError):
    """An access denial or rate limit requiring this run to stop requests."""


_last_request = 0.0
_RETRYABLE = {429, 500, 502, 503, 504}
_BLOCK_MESSAGES = (
    "your request originates from an undeclared automated tool",
    "request rate threshold exceeded",
    "your request has been identified as part of a network of automated tools",
)


def validate_headers(headers):
    agent = next((v for k, v in headers.items() if k.lower() == "user-agent"), "")
    if not re.search(r"[^\s@]+@[^\s@]+\.[^\s@]+", agent) or "example.com" in agent.lower():
        raise ValueError("Set SEC_HEADERS User-Agent to a project name and real contact email.")


def validate_html(html):
    if not isinstance(html, str) or not html.strip():
        raise ValueError("SEC returned an empty filing document")
    lowered = html.lower()
    if any(message in lowered for message in _BLOCK_MESSAGES):
        raise SecAccessError("SEC returned an access-block page instead of a filing. Stop and review SEC access guidance.")
    if not re.search(r"<(?:html|body|head|!doctype)\b", lowered):
        raise ValueError("Expected a filing HTML document")
    return html


def _retry_delay(response, attempt):
    value = response.headers.get("Retry-After") if response is not None else None
    if value:
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                date = parsedate_to_datetime(value)
                return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError):
                pass
    return float(2 ** (attempt - 1))


def get_sec_response(url, headers, maximum_attempts=3):
    global _last_request
    validate_headers(headers)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc not in {"www.sec.gov", "data.sec.gov"}:
        raise ValueError("Expected an HTTPS SEC URL")
    if not isinstance(maximum_attempts, int) or maximum_attempts < 1:
        raise ValueError("maximum_attempts must be a positive integer")
    for attempt in range(1, maximum_attempts + 1):
        # At most five request starts/second within this sequential process.
        time.sleep(max(0.0, 0.2 - (time.monotonic() - _last_request)))
        _last_request = time.monotonic()
        response = None
        try:
            response = requests.get(url, headers=headers, timeout=(10, 45), allow_redirects=False)
            if response.status_code == 403:
                raise SecAccessError(
                    "SEC access denied (HTTP 403). Check the identifying contact header, "
                    "request rate and network/IP access; no automatic retry was made.",
                    response=response
                )
            response.raise_for_status()
            if 300 <= response.status_code < 400:
                raise requests.HTTPError("Unexpected SEC redirect; refusing to cache redirect content", response=response)
            return response
        except (requests.ConnectionError, requests.Timeout):
            if attempt == maximum_attempts:
                raise
        except requests.HTTPError:
            if response is not None and response.status_code == 429 and attempt == maximum_attempts:
                raise SecAccessError("SEC rate limit persists (HTTP 429); stop requests and rerun later.", response=response)
            if response is None or response.status_code not in _RETRYABLE or attempt == maximum_attempts:
                raise
        delay = _retry_delay(response, attempt)
        if delay > 60:
            raise SecAccessError("SEC requested a retry after more than 60 seconds; stop requests and rerun later", response=response)
        print(f"Transient SEC request failure; retry {attempt + 1}/{maximum_attempts} in {delay:g}s.")
        time.sleep(delay)
