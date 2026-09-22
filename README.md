# Agent Hands

A small computer-use system: an LLM discovers a UI workflow, a typed capability records it, and an independent engine replays it without model calls. Includes a fictional legacy-style banking app and real same-session browser handoff.

**Verified demonstration:** the submitted evidence records live discovery with `gpt-4.1-mini`, replay of the learned artifact for a different member, a member-not-found business outcome, human takeover and verified resume, and a 120-second handoff timeout. See [the evidence index](evidence/README.md) for file-level provenance and limitations. `artifacts/discovered.json` is the learned capability; `artifacts/fixture.json` remains a hand-authored test fixture.

## Recorded results

| Scenario | Result | Evidence |
| --- | --- | --- |
| Live discovery | Three UI actions and verified completion | `evidence/discovery-fixed/events.jsonl` |
| Learned replay | Success; caller observed 9876.54 USD for member 67890 | `evidence/learned-replay/events.jsonl` |
| Unknown member | `business_outcome / member_not_found` | `evidence/learned-not-found/events.jsonl` |
| Human takeover | Unlock click, checkpoint verification, successful continuation | `evidence/handoff-success/events.jsonl` |
| Timeout | Second run pauses after 120.16 seconds | `evidence/handoff-timeout/events.jsonl` |

Balances and member values are intentionally absent from persistent event logs. The replay balance above was observed in terminal output.

## Setup

Python 3.11+ on a desktop with a browser display for human takeover.

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -e . pytest
python -m playwright install chromium
# Linux missing browser system libraries: python -m playwright install-deps chromium
```

Terminal 1, leave running:

```bash
hands serve
```

Open http://127.0.0.1:8765/ to inspect the fictional app. Known members: `12345` and `67890`; `00000` does not exist. No real credentials or PII.

## Required live discovery → replay demo

Set `OPENAI_API_KEY` in your local environment without saving it in a file or repository. The recorded run used `gpt-4.1-mini` with Chat Completions strict structured output. The request schema is derived from the Pydantic decision contract; local validation and policy checks still run before execution. The implementation sends structural state and the goal to the model, not the member value or balance. Do not put private data in the goal.

```bash
hands discover --model gpt-4.1-mini --member-id 12345 --artifact artifacts/discovered.json --evidence runs/new-discovery --headed
hands replay --member-id 67890 --artifact artifacts/discovered.json --evidence runs/new-replay --headed
hands replay --member-id 00000 --artifact artifacts/discovered.json --evidence runs/new-not-found
```

The first command must complete successfully and emit `provenance: live_llm`. There is no fake-model fallback. Review the artifact before replay. Outputs are printed as JSON to stdout; evidence deliberately excludes output values.

## Offline-service demo (real browser, no model)

```bash
hands replay --member-id 67890 --artifact artifacts/fixture.json --evidence runs/success
hands replay --member-id 00000 --artifact artifacts/fixture.json --evidence runs/not-found
hands replay --url "http://127.0.0.1:8765/?scenario=slow" --member-id 12345 --artifact artifacts/fixture.json --evidence runs/slow
```

## Human takeover on the same session

```bash
hands replay --url "http://127.0.0.1:8765/?scenario=blocked" --member-id 67890 --artifact artifacts/discovered.json --evidence runs/handoff --headed --interactive
```

When the terminal reports PAUSED, automation has ceded control. In that same browser window click **Unlock session**. Leave the page at **Member detail**, then type `resume` in the original terminal within 120 seconds. To test timeout separately, leave both browser and terminal untouched for 120 seconds. The controller checks `Member detail` before returning ownership to automation; the run continues to Savings. Click/input/change event types and navigation occurrence are recorded without entered values. `abort`, failed verification, or timeout leaves the run paused and the CLI then closes the session. The browser also closes automatically after successful completion. Sessions are not durable across process exits.

Use `?scenario=denied` to demonstrate a permission-denied escalation. Do not bypass permission denial; abort the demonstration. Unexpected dialogs or blocked network requests stop execution and require a new run after investigation.

## Tests

```bash
python -m pytest -q
# Unit tests only (when the environment cannot launch a browser):
python -m pytest -q -m "not browser"
```

Tests cover schema/input validation, destination policy, risky actions, genuine browser replays with different inputs, not-found outcomes, slow loading, ambiguous targeting, sanitized logging, and same-session control transfer with a **simulated operator**. This automated operator test does not pretend to be human evidence.

## Structure

- `hands/schema.py`: typed capability and result contracts; exported JSON Schema in `artifacts/`.
- `hands/surface.py`, `policy.py`: browser adapter and code-owned policy.
- `hands/discovery.py`: real model client and bounded discovery loop.
- `hands/engine.py`: independent deterministic replay.
- `hands/handoff.py`: live ownership transfer and verified resume.
- `hands/demo.py`: standard-library HTTP target with no automation API.
- `REPORT.md`: architecture, trade-offs, limits, and next steps.

## Submission

The recorded live evidence is indexed in `evidence/README.md`. Reproduction commands write to `runs/` so they do not append to the submitted evidence; the discovery command replaces `artifacts/discovered.json`, so use a different artifact path if retaining the original. Push source, artifacts and sanitized evidence to a public GitHub repository. Do not commit `.venv`, credentials, raw traces or `runs/`. Email the repository URL on its own line to assignments@interface.ai using the address you applied with. This project has not been published or emailed automatically.
