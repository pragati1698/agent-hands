import json, time
from pathlib import Path


class Evidence:
    """Allowlisted metadata only; never persist raw DOM, goal, parameters or output values."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def event(self, event, **fields):
        with (self.path / "events.jsonl").open("a") as f:
            f.write(json.dumps({"time": time.time(), "event": event, **fields}) + "\n")

    def failure(self, observation):
        # Richer than a log line: sanitized structural state and control inventory.
        (self.path / "failure-state.json").write_text(json.dumps(observation, indent=2))
