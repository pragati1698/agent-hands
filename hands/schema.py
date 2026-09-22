from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Target(Contract):
    strategy: Literal["label", "role", "text"]
    value: str
    role: str | None = None


class Step(Contract):
    action: Literal["click", "type"]
    target: Target
    parameter: str | None = None
    checkpoint: Literal["Member search", "Member detail", "Savings account"]

    @model_validator(mode="after")
    def valid_binding(self):
        if self.action == "type" and not self.parameter:
            raise ValueError("Typing requires an explicit input parameter")
        if self.action == "click" and self.parameter:
            raise ValueError("Click cannot bind a parameter")
        return self


class Output(Contract):
    type: Literal["decimal", "currency"]
    target: Target


class Capability(Contract):
    schema_version: Literal["1.0"] = "1.0"
    artifact_version: Literal["1.0.0"] = "1.0.0"
    name: str = "read_savings_balance"
    app_family: Literal["ledger-demo"] = "ledger-demo"
    app_version: Literal["1"] = "1"
    provenance: Literal["fixture", "live_llm"]
    inputs: dict[str, Literal["member_id"]] = {"member_id": "member_id"}
    steps: list[Step] = Field(min_length=1, max_length=20)
    outputs: dict[str, Output]
    success: Literal["Savings account"] = "Savings account"
    business_outcomes: dict[str, str] = {
        "Member not found": "member_not_found",
        "Validation error": "invalid_member_id",
    }

    @model_validator(mode="after")
    def contract(self):
        if self.inputs != {"member_id": "member_id"}:
            raise ValueError("This version supports the member_id contract only")
        if set(self.outputs) != {"balance", "currency"}:
            raise ValueError("Balance and currency outputs required")
        if (
            self.outputs["balance"].type != "decimal"
            or self.outputs["currency"].type != "currency"
        ):
            raise ValueError("Incorrect output types")
        if self.outputs["balance"].target != Target(
            strategy="label", value="Balance"
        ) or self.outputs["currency"].target != Target(
            strategy="label", value="Currency"
        ):
            raise ValueError("Output targets must match approved profile")
        if any(s.parameter and s.parameter not in self.inputs for s in self.steps):
            raise ValueError("Unbound input")
        return self


class Result(Contract):
    status: Literal["success", "business_outcome", "failure", "paused"]
    code: str
    outputs: dict[str, str] = {}
    step: int | None = None
    expected: str | None = None
    observed: str | None = None
