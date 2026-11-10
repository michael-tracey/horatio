"""Links people type in, to be shown as links: only web addresses, so a link can never
run script (javascript:) or open something else."""

from urllib.parse import urlsplit

from fastapi import HTTPException, status


def is_web_address(url: str, longest: int = 300) -> bool:
    """`url`, trimmed, is an http or https address with a host."""
    url = url.strip()
    try:
        parts = urlsplit(url)
    except ValueError:  # a broken IPv6 host, such as http://[x
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc) and len(url) <= longest


def web_address(url: str, longest: int = 300) -> str:
    """`url` trimmed, if it is an http or https address; refused otherwise, so a
    link can never run script (javascript:) or open something else."""
    url = url.strip()
    if not is_web_address(url, longest):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{url or 'A link'} is not a web address: start it with https://.",
        )
    return url


def optional_web_address(url: str, longest: int = 300) -> str:
    """`url` trimmed: empty for none, else a web address, refused otherwise."""
    return web_address(url, longest) if url.strip() else ""
