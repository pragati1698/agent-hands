from typing import Protocol
from .schema import Step, Target
from .policy import Policy, PolicyError

STATES = [
    "Member search",
    "Member detail",
    "Savings account",
    "Member not found",
    "Validation error",
    "Permission denied",
    "Session locked",
    "Loading",
]


class Surface(Protocol):
    def observe(self) -> dict: ...
    def act(self, step: Step, inputs: dict) -> None: ...
    def check(self, state: str) -> bool: ...
    def extract(self, target: Target) -> str: ...


class BrowserSurface:
    def __init__(self, page, policy: Policy):
        self.page = page
        self.policy = policy
        self.blocked = False
        self.owner = "automation"
        page.context.route("**/*", self._route)
        page.on("dialog", self._dialog)

    def _dialog(self, dialog):
        self.blocked = True
        dialog.dismiss()

    def _route(self, route):
        try:
            self.policy.url(route.request.url)
            if route.request.method != "GET":
                raise PolicyError("Only GET permitted")
            route.continue_()
        except PolicyError:
            self.blocked = True
            route.abort()

    def start(self, url):
        self.policy.url(url)
        self.page.goto(url, wait_until="domcontentloaded")
        if not self.page.get_by_text(
            "Fictional data · training environment · app version 1", exact=True
        ).count():
            raise PolicyError("App compatibility check failed")

    def locator(self, t):
        if t.strategy == "label":
            return self.page.get_by_label(t.value, exact=True)
        if t.strategy == "role":
            return self.page.get_by_role(t.role or "button", name=t.value, exact=True)
        return self.page.get_by_text(t.value, exact=True)

    def check(self, state):
        return self.page.get_by_role("heading", name=state, exact=True).is_visible()

    def observe(self):
        # Only approved structural labels leave the surface. Values remain in memory.
        self.policy.url(self.page.url)
        states = [s for s in STATES if self.check(s)]
        controls = []
        for t in [
            Target(strategy="label", value="Member ID"),
            Target(strategy="role", role="button", value="Search"),
            Target(strategy="role", role="link", value="Savings"),
        ]:
            loc = self.locator(t)
            if loc.count() == 1 and loc.is_visible():
                controls.append(t.model_dump(exclude_none=True))
        return {"states": states, "controls": controls, "policy_blocked": self.blocked}

    def snapshot(self):
        return {
            **self.observe(),
            "structure": self.page.evaluate(
                """()=>Array.from(document.body.querySelectorAll('h1,h2,table,tr,td,form,label,input,button,a,output')).slice(0,100).map(e=>({tag:e.tagName.toLowerCase(),visible:!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length),children:e.children.length}))"""
            ),
        }

    def act(self, step, inputs):
        if self.owner != "automation":
            raise PolicyError("Human owns session")
        if self.blocked:
            raise PolicyError("Unexpected dialog or blocked request")
        self.policy.url(self.page.url)
        self.policy.action(step)
        required_state = (
            "Member detail" if step.target.value == "Savings" else "Member search"
        )
        if not self.check(required_state):
            raise PolicyError("Action precondition absent")
        loc = self.locator(step.target)
        if loc.count() != 1:
            raise PolicyError("Target must resolve uniquely")
        if step.action == "type":
            loc.fill(inputs[step.parameter], timeout=3000)
        else:
            loc.click(timeout=3000)
        self.policy.url(self.page.url)
        if self.blocked:
            raise PolicyError("Blocked request or unexpected dialog")

    def wait_state(self, state, timeout=3000):
        self.page.get_by_role("heading", name=state, exact=True).wait_for(
            state="visible", timeout=timeout
        )

    def extract(self, target):
        loc = self.locator(target)
        if loc.count() != 1:
            raise PolicyError("Ambiguous output")
        return loc.inner_text(timeout=3000).strip()
