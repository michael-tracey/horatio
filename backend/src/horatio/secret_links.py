"""Links with a secret in them, kept out of the logs (issue #1060).

A password reset, an email change, an NPC's claim, an unsubscribe, a calendar and a
check-in link each carry a bearer credential in their path: whoever has the address
can use it. So the access logs write REDACTED in the secret's place: the app's own
(uvicorn's, which production sends to Cloud Logging) through `RedactSecrets`, and
nginx's through the same patterns in deploy/nginx-horatio.conf.j2. Discord's callback
carries its one-time code and state in the query, so its query goes too.

A new link with a secret in it goes in PATTERNS and in nginx's map;
tests/test_secret_links.py fails until it is in both.
"""

import logging
import re

REDACTED = "REDACTED"

# The first that matches the request's path and query gives what is logged, as
# nginx's map does: a pattern's captures are kept, and the rest dropped.
PATTERNS = [
    # The frontend's pages and the API's routes whose next segment is the secret.
    (
        re.compile(
            r"^(/(?:reset-password|confirm-email|unsubscribe|claim|check-in|api/auth/reset"
            r"|api/auth/email-change|api/unsubscribe|api/claims|api/checkin)/)[^/?]+([^?]*)"
        ),
        rf"\1{REDACTED}\2",
    ),
    (re.compile(r"^(/api/calendar/)[^/?]+(\.ics)"), rf"\1{REDACTED}\2"),
    (re.compile(r"^(/api/discord/callback)\?"), rf"\1?{REDACTED}"),
]


def redact(target: str) -> str:
    """A request's path and query as it may be logged."""
    for pattern, logged in PATTERNS:
        found = pattern.match(target)
        if found:
            return found.expand(logged)
    return target


class RedactSecrets(logging.Filter):
    """For uvicorn's access log, whose third argument is the path and query."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) > 2 and isinstance(args[2], str):
            record.args = (*args[:2], redact(args[2]), *args[3:])
        return True
