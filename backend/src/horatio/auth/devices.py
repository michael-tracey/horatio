"""Telling someone where they're signed in, in plain words (#1193): the browser and
system a User-Agent names, and roughly where an address is.

Both are guesses, kept simple on purpose. A User-Agent says what the browser wants
it to; this only has to tell "Firefox on Windows" from "Safari on iPhone"."""

import ipaddress

# The browser, by the first of these its User-Agent has. Order matters: Edge and
# Opera say "Chrome" too, and Chrome says "Safari".
BROWSERS: tuple[tuple[str, str], ...] = (
    ("Edg", "Edge"),
    ("OPR/", "Opera"),
    ("Opera", "Opera"),
    ("SamsungBrowser/", "Samsung Internet"),
    ("Firefox/", "Firefox"),
    ("FxiOS/", "Firefox"),
    ("CriOS/", "Chrome"),
    ("Chrome/", "Chrome"),
    ("Chromium/", "Chrome"),
    ("Safari/", "Safari"),
)

# The system, likewise. An iPhone's and an Android phone's also say "Mac OS X" and
# "Linux".
SYSTEMS: tuple[tuple[str, str], ...] = (
    ("iPhone", "iPhone"),
    ("iPad", "iPad"),
    ("Android", "Android"),
    ("CrOS", "ChromeOS"),
    ("Windows", "Windows"),
    ("Macintosh", "Mac"),
    ("Mac OS X", "Mac"),
    ("Linux", "Linux"),
)


def first_named(user_agent: str, names: tuple[tuple[str, str], ...]) -> str | None:
    return next((name for mark, name in names if mark in user_agent), None)


def device(user_agent: str | None) -> str:
    """The browser and system a User-Agent names: "Firefox on Windows", "Safari on
    iPhone", or as much as it says."""
    browser = first_named(user_agent or "", BROWSERS)
    system = first_named(user_agent or "", SYSTEMS)
    if browser and system:
        return f"{browser} on {system}"
    if browser:
        return browser
    if system:
        return f"A browser on {system}"
    return "An unknown browser"


def place(ip: str | None) -> str | None:
    """An address shown coarsely: its network, not the one machine. "203.0.113.…" for
    an IPv4 address (its /24), "2001:db8:85a3:…" for IPv6 (its /48)."""
    if not ip:
        return None
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv4Address):
        return ".".join(ip.split(".")[:3]) + ".…"
    network = ipaddress.ip_network(f"{address}/48", strict=False)
    groups = network.network_address.exploded.split(":")[:3]
    return ":".join(g.lstrip("0") or "0" for g in groups) + ":…"
