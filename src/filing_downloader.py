from src.sec_http import get_sec_response, validate_html


def download_filing_html(filing_url, headers, maximum_attempts=3):
    response = get_sec_response(filing_url, headers, maximum_attempts)
    content_type = response.headers.get("Content-Type", "").lower()
    if content_type and not any(kind in content_type for kind in ("text/html", "application/xhtml+xml")):
        raise ValueError(f"Expected filing HTML, received {content_type.split(';')[0]}")
    return validate_html(response.text)
