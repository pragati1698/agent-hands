import argparse, json, sys
from pathlib import Path
from .schema import Capability


def main():
    parser = argparse.ArgumentParser(description="Learn once, replay without a model")
    commands = parser.add_subparsers(dest="command", required=True)
    app = commands.add_parser("serve")
    app.add_argument("--port", type=int, default=8765)
    for name in ("discover", "replay"):
        p = commands.add_parser(name)
        p.add_argument("--url", default="http://127.0.0.1:8765/")
        p.add_argument("--member-id", required=True)
        p.add_argument("--artifact", default="artifacts/discovered.json")
        p.add_argument("--evidence", required=True)
        p.add_argument("--headed", action="store_true")
        p.add_argument("--interactive", action="store_true")
        if name == "discover":
            p.add_argument(
                "--goal",
                default="Find the supplied member and read their savings balance",
            )
            p.add_argument("--model", required=True)
    args = parser.parse_args()
    if args.command == "serve":
        from .demo import serve

        serve(args.port)
        return
    if args.interactive and not args.headed:
        parser.error("--interactive requires --headed")
    from playwright.sync_api import sync_playwright
    from .policy import Policy
    from .surface import BrowserSurface
    from .evidence import Evidence
    from .handoff import Handoff
    from .engine import replay, validate_inputs

    inputs = {"member_id": args.member_id}
    try:
        validate_inputs(inputs)
    except ValueError:
        print('{"status":"business_outcome","code":"invalid_member_id"}')
        return
    evidence = Evidence(args.evidence)
    if args.command == "discover":
        from .discovery import discover, OpenAIModel

        model = OpenAIModel(
            args.model
        )  # Fail before starting browser if key is absent.
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chromium", headless=not args.headed)
        context = browser.new_context(service_workers="block")
        surface = BrowserSurface(context.new_page(), Policy(args.url))
        handoff = Handoff(evidence, enabled=args.interactive)
        try:
            surface.start(args.url)
            if args.command == "discover":
                cap = discover(surface, args.goal, inputs, model, evidence, handoff)
                dest = Path(args.artifact)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(cap.model_dump_json(indent=2))
                print(json.dumps({"status": "success", "artifact": str(dest)}))
            else:
                cap = Capability.model_validate_json(Path(args.artifact).read_text())
                result = replay(surface, cap, inputs, evidence, handoff)
                # Outputs go to caller stdout, not persistent evidence.
                print(result.model_dump_json(indent=2))
                evidence.event(
                    "result", status=result.status, code=result.code, step=result.step
                )
                if result.status in ("failure", "paused"):
                    sys.exit(2)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
