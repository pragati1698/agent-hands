from urllib.parse import urlparse
from .schema import Step


class PolicyError(Exception):
    pass


class Policy:
    """Code-owned policy; artifacts and model responses cannot widen it."""

    def __init__(self, base_url):
        p = urlparse(base_url)
        if (
            p.scheme != "http"
            or p.hostname not in ("localhost", "127.0.0.1")
            or p.username
            or p.password
        ):
            raise PolicyError("Demo policy permits only local HTTP targets")
        self.origin = (p.scheme, p.hostname, p.port)

    def url(self, url):
        p = urlparse(url)
        if (
            (p.scheme, p.hostname, p.port) != self.origin
            or p.path not in ("/", "/member", "/savings")
            or p.username
            or p.password
        ):
            raise PolicyError("Destination outside configured allowlist")

    def action(self, step: Step):
        t = step.target
        allowed = (
            step.action == "type"
            and t.strategy == "label"
            and t.value == "Member ID"
            and step.parameter == "member_id"
        ) or (
            step.action == "click"
            and t.strategy == "role"
            and (t.role, t.value) in [("button", "Search"), ("link", "Savings")]
        )
        if not allowed:
            raise PolicyError("Operation is not approved for this read-only capability")
