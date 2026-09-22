"""A real local handoff: headed browser + CLI, with one session owner."""

import queue, threading, time


class Handoff:
    def __init__(self, evidence, enabled=False, operator=None, timeout=120):
        self.evidence = evidence
        self.enabled = enabled
        self.operator = operator
        self.timeout = timeout

    def request(
        self, surface, step, expected, reason, capability="read_savings_balance"
    ):
        obs = surface.observe()
        self.evidence.failure(surface.snapshot())
        self.evidence.event(
            "intervention_requested",
            capability=capability,
            step=step,
            expected=expected,
            reason=reason,
            observation=obs,
        )
        surface.owner = "paused"
        if not self.enabled:
            return False
        surface.owner = "human"
        self.evidence.event("control_transferred", owner="human")
        # Listener is reinstalled after each navigation, preserving the live context.
        name = "reportHumanAction"
        if not getattr(surface, "human_binding", False):

            def capture(source, event):
                if (
                    surface.owner == "human"
                    and isinstance(event, dict)
                    and event.get("action") in ("click", "input", "change")
                ):
                    target = event.get("target")
                    if target not in (
                        "Unlock session",
                        "Member ID",
                        "Search",
                        "Savings",
                    ):
                        target = "unclassified control"
                    self.evidence.event(
                        "human_action", action=event["action"], target=target
                    )

            surface.page.expose_binding(name, capture)
            script = """(()=>{if(window.__handsListening)return;window.__handsListening=true;for(const e of ['click','input','change'])document.addEventListener(e,event=>{const el=event.target.closest('a,button,input');const text=el?(el.tagName==='INPUT'?'Member ID':el.textContent.trim()):'';window.reportHumanAction({action:e,target:['Unlock session','Member ID','Search','Savings'].includes(text)?text:'unclassified control'})},true)})()"""
            surface.page.context.add_init_script(script)
            surface.page.evaluate(script)
            surface.human_binding = True
        start_url = surface.page.url
        try:
            if self.operator:
                self.operator(surface)
            else:
                print(
                    f"PAUSED at step {step}: {reason}. Use the SAME browser window. Then type resume or abort (120s limit).",
                    flush=True,
                )
                response = queue.Queue()
                threading.Thread(
                    target=lambda: response.put(input("operator> ").strip()),
                    daemon=True,
                ).start()
                deadline = time.monotonic() + self.timeout
                while response.empty() and time.monotonic() < deadline:
                    surface.page.wait_for_timeout(
                        100
                    )  # Pump browser events while operator acts.
                if response.empty() or response.get() != "resume":
                    return False
            if surface.page.url != start_url:
                self.evidence.event(
                    "human_navigation", destination="allowlisted target; query omitted"
                )
            surface.policy.url(surface.page.url)
            if surface.blocked:
                return False
            surface.wait_state(expected)
            self.evidence.event("resume_verified", step=step, checkpoint=expected)
            surface.owner = "automation"
            return True
        except Exception as exc:
            self.evidence.event("resume_rejected", error_type=type(exc).__name__)
            return False
        finally:
            if surface.owner != "automation":
                surface.owner = "paused"
