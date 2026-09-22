"""Replay has no model import or client: only the reviewed artifact drives it."""

from decimal import Decimal
import re, time
from .schema import Result

BUSINESS = {
    "Member not found": "member_not_found",
    "Validation error": "invalid_member_id",
}


def validate_inputs(inputs):
    if (
        set(inputs) != {"member_id"}
        or not isinstance(inputs["member_id"], str)
        or not re.fullmatch(r"[0-9]{5}", inputs["member_id"])
    ):
        raise ValueError("member_id must be a five-digit string")


def after_action(surface, step, index, evidence, handoff):
    deadline = time.monotonic() + 4
    saw_loading = False
    while time.monotonic() < deadline:
        obs = surface.observe()
        if obs["policy_blocked"]:
            raise RuntimeError("policy_blocked")
        for state, code in BUSINESS.items():
            if state in obs["states"]:
                return Result(status="business_outcome", code=code, step=index)
        if step.checkpoint in obs["states"]:
            if saw_loading:
                evidence.event(
                    "recovery_completed", step=index, rule="bounded_loading_wait"
                )
            evidence.event(
                "checkpoint_verified", step=index, checkpoint=step.checkpoint
            )
            return None
        if "Loading" in obs["states"]:
            if not saw_loading:
                evidence.event(
                    "recovery_started", step=index, rule="bounded_loading_wait"
                )
            saw_loading = True
        elif any(x in obs["states"] for x in ["Permission denied", "Session locked"]):
            break
        surface.page.wait_for_timeout(100)
    if handoff.request(surface, index, step.checkpoint, "checkpoint_not_reached"):
        return None
    return Result(
        status="paused",
        code="intervention_required",
        step=index,
        expected=step.checkpoint,
        observed=",".join(surface.observe()["states"]) or "unrecognized_state",
    )


def extract_outputs(surface, capability):
    if not surface.check(capability.success):
        raise ValueError("Final success condition absent")
    outputs = {}
    for name, spec in capability.outputs.items():
        value = surface.extract(spec.target)
        if spec.type == "decimal":
            if (
                not re.fullmatch(r"-?[0-9]+\.[0-9]{2}", value)
                or not Decimal(value).is_finite()
            ):
                raise ValueError("Invalid decimal output")
        elif not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("Invalid currency output")
        outputs[name] = value
    return outputs


def replay(surface, capability, inputs, evidence, handoff):
    index = None
    try:
        validate_inputs(inputs)
        if capability.business_outcomes != BUSINESS:
            raise ValueError("Unsupported business rules")
        # Validate entire artifact before any action, including downstream steps.
        for step in capability.steps:
            surface.policy.action(step)
        for index, step in enumerate(capability.steps):
            evidence.event("action_started", step=index, action=step.action)
            surface.act(step, inputs)
            outcome = after_action(surface, step, index, evidence, handoff)
            if outcome:
                return outcome
        outputs = extract_outputs(surface, capability)
        evidence.event("run_completed", status="success", output_names=list(outputs))
        return Result(status="success", code="completed", outputs=outputs)
    except Exception as exc:
        # Exception messages from browser drivers can contain input values.
        evidence.event("run_failed", step=index, error_type=type(exc).__name__)
        try:
            expected = (
                capability.steps[index].checkpoint
                if index is not None
                else "Member search"
            )
            if index is not None:
                handoff.request(surface, index, expected, "execution_failure")
            evidence.failure(surface.snapshot())
        except Exception:
            pass
        return Result(
            status="failure",
            code=type(exc).__name__,
            step=index,
            expected="valid input and approved action at expected state",
            observed="See sanitized failure-state.json",
        )
