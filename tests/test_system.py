import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
import pytest
from hands.schema import Capability, Step, Target
from hands.policy import Policy, PolicyError
from hands.demo import Handler
from hands.engine import replay, validate_inputs
from hands.evidence import Evidence
from hands.handoff import Handoff

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def capability():
    return Capability.model_validate_json((ROOT / "artifacts/fixture.json").read_text())


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "http://127.0.0.1:9999/",
        "http://127.0.0.1:8765/admin",
        "http://user:pass@127.0.0.1:8765/",
    ],
)
def test_destination_policy(url):
    with pytest.raises(PolicyError):
        Policy("http://127.0.0.1:8765/").url(url)


def test_risky_action_blocked():
    with pytest.raises(PolicyError):
        Policy("http://localhost:8765/").action(
            Step(
                action="click",
                target=Target(strategy="role", role="button", value="Create account"),
                checkpoint="Member detail",
            )
        )


@pytest.mark.parametrize("member", [12345, "1234", "１２３４５", "123456", "<script>"])
def test_input_validation(member):
    with pytest.raises(ValueError):
        validate_inputs({"member_id": member})


def test_schema_rejects_unbound_parameter(capability):
    data = capability.model_dump()
    data["steps"][0]["parameter"] = "secret"
    with pytest.raises(ValueError):
        Capability.model_validate(data)


def test_schema_rejects_version(capability):
    data = capability.model_dump()
    data["schema_version"] = "2.0"
    with pytest.raises(ValueError):
        Capability.model_validate(data)


def test_replay_has_no_model_dependency():
    import ast

    module = ast.parse((ROOT / "hands/engine.py").read_text())
    imports = [
        node.module for node in ast.walk(module) if isinstance(node, ast.ImportFrom)
    ]
    assert "discovery" not in imports


@pytest.fixture(scope="module")
def target():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()
    server.server_close()


@pytest.fixture
def surface(target):
    from playwright.sync_api import sync_playwright
    from hands.surface import BrowserSurface

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chromium")
        context = browser.new_context(service_workers="block")
        surf = BrowserSurface(context.new_page(), Policy(target))
        surf.start(target)
        yield surf
        browser.close()


@pytest.mark.parametrize(
    "member,expected", [("12345", "1520.25"), ("67890", "9876.54")]
)
@pytest.mark.browser
def test_real_browser_replay(surface, capability, tmp_path, member, expected):
    evidence = Evidence(tmp_path)
    result = replay(
        surface, capability, {"member_id": member}, evidence, Handoff(evidence)
    )
    assert result.status == "success"
    assert result.outputs == {"balance": expected, "currency": "USD"}
    assert member not in (tmp_path / "events.jsonl").read_text()
    assert expected not in (tmp_path / "events.jsonl").read_text()


@pytest.mark.browser
def test_not_found(surface, capability, tmp_path):
    evidence = Evidence(tmp_path)
    result = replay(
        surface, capability, {"member_id": "00000"}, evidence, Handoff(evidence)
    )
    assert result.status == "business_outcome"
    assert result.code == "member_not_found"


@pytest.mark.browser
def test_slow_load(surface, target, capability, tmp_path):
    surface.start(target + "?scenario=slow")
    evidence = Evidence(tmp_path)
    result = replay(
        surface, capability, {"member_id": "12345"}, evidence, Handoff(evidence)
    )
    assert result.status == "success"
    assert "recovery_completed" in (tmp_path / "events.jsonl").read_text()


@pytest.mark.browser
def test_same_session_handoff(surface, target, capability, tmp_path):
    surface.start(target + "?scenario=blocked")
    evidence = Evidence(tmp_path)
    original = surface.page

    def operator(s):
        assert s.owner == "human"
        assert s.page is original
        with pytest.raises(PolicyError):
            s.act(capability.steps[0], {"member_id": "12345"})
        s.page.get_by_role("link", name="Unlock session", exact=True).click()

    result = replay(
        surface,
        capability,
        {"member_id": "12345"},
        evidence,
        Handoff(evidence, enabled=True, operator=operator),
    )
    assert result.status == "success"
    assert surface.owner == "automation"
    log = (tmp_path / "events.jsonl").read_text()
    assert "human_action" in log
    assert "resume_verified" in log


@pytest.mark.browser
def test_denied_pauses(surface, target, capability, tmp_path):
    surface.start(target + "?scenario=denied")
    evidence = Evidence(tmp_path)
    result = replay(
        surface, capability, {"member_id": "12345"}, evidence, Handoff(evidence)
    )
    assert result.status == "paused"
    assert surface.owner == "paused"
    assert (tmp_path / "failure-state.json").exists()


@pytest.mark.browser
def test_ambiguous_target_stops(surface, capability, tmp_path):
    surface.page.evaluate(
        "document.querySelector('form').insertAdjacentHTML('beforeend','<button>Search</button>')"
    )
    evidence = Evidence(tmp_path)
    result = replay(
        surface, capability, {"member_id": "12345"}, evidence, Handoff(evidence)
    )
    assert result.status == "failure"


@pytest.mark.browser
def test_failed_resume_does_not_transfer_control(surface, target, capability, tmp_path):
    surface.start(target + "?scenario=blocked")
    evidence = Evidence(tmp_path)
    result = replay(
        surface,
        capability,
        {"member_id": "12345"},
        evidence,
        Handoff(evidence, enabled=True, operator=lambda s: None),
    )
    assert result.status == "paused"
    assert surface.owner == "paused"


class StubSurface:
    """Unit-test double only. Never used by CLI or written as live evidence."""

    def __init__(self, states):
        self.policy = Policy("http://localhost:8765/")
        self.states = iter(states)
        self.state = "Member search"
        self.actions = []
        self.owner = "automation"
        self.page = self

    def act(self, step, inputs):
        self.actions.append(step)
        self.state = next(self.states)

    def observe(self):
        return {"states": [self.state], "controls": [], "policy_blocked": False}

    def snapshot(self):
        return self.observe()

    def check(self, state):
        return state == self.state

    def extract(self, target):
        return "42.00" if target.value == "Balance" else "USD"

    def wait_for_timeout(self, ms):
        pass


def test_replay_logic_success(capability, tmp_path):
    surface = StubSurface(["Member search", "Member detail", "Savings account"])
    e = Evidence(tmp_path)
    result = replay(surface, capability, {"member_id": "12345"}, e, Handoff(e))
    assert result.status == "success"
    assert result.outputs["balance"] == "42.00"


def test_replay_logic_business_stops_before_next_action(capability, tmp_path):
    surface = StubSurface(["Member search", "Member not found"])
    e = Evidence(tmp_path)
    result = replay(surface, capability, {"member_id": "00000"}, e, Handoff(e))
    assert result.code == "member_not_found"
    assert len(surface.actions) == 2


def test_replay_logic_denial_pauses(capability, tmp_path):
    surface = StubSurface(["Member search", "Permission denied"])
    e = Evidence(tmp_path)
    result = replay(surface, capability, {"member_id": "12345"}, e, Handoff(e))
    assert result.status == "paused"
    assert surface.owner == "paused"


def test_replay_rejects_whole_unsafe_artifact_before_acting(capability, tmp_path):
    data = capability.model_dump()
    data["steps"][-1]["target"]["value"] = "Create account"
    cap = Capability.model_validate(data)
    surface = StubSurface([])
    e = Evidence(tmp_path)
    result = replay(surface, cap, {"member_id": "12345"}, e, Handoff(e))
    assert result.status == "failure"
    assert surface.actions == []


def test_invalid_output_is_not_success(capability, tmp_path):
    surface = StubSurface(["Member search", "Member detail", "Savings account"])
    surface.extract = lambda target: "NaN"
    e = Evidence(tmp_path)
    result = replay(surface, capability, {"member_id": "12345"}, e, Handoff(e))
    assert result.status == "failure"
