"""Atrium CLI — serve, scaffold, and run examples."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path


def cmd_serve(args):
    import uvicorn
    from atrium.api.app import create_app
    from atrium.core.registry import AgentRegistry
    from atrium.engine.llm import detect_llm

    llm_config = args.llm or detect_llm()
    app = create_app(registry=AgentRegistry(), llm_config=llm_config)
    print(f"Atrium serving at http://{args.host}:{args.port}")
    print(f"LLM: {llm_config}")
    uvicorn.run(app, host=args.host, port=args.port)


def cmd_version(args):
    import atrium
    print(f"atrium {atrium.__version__}")


def cmd_example_run(args):
    """Run a bundled example."""
    name = args.name
    if name == "hello_world":
        from atrium.examples.hello_world.app import app
        app.serve()
    elif name == "observe":
        from atrium.examples.observe.app import app
        app.serve()
    else:
        print(f"Unknown example: {name}")
        print("Available examples: hello_world, observe")
        sys.exit(1)


def cmd_agents_list(args):
    """List agents from bundled examples."""
    print("Built-in example agents:\n")
    print("hello_world:")
    from atrium.examples.hello_world.agents import WikiSearchAgent, SummarizerAgent, FactCheckerAgent
    for a in [WikiSearchAgent, SummarizerAgent, FactCheckerAgent]:
        print(f"  {a.name:20s} {a.description}")

    print("\nobserve:")
    from atrium.examples.observe.agents.pathfinder import PathfinderAgent
    from atrium.examples.observe.agents.mapper import MapperAgent
    from atrium.examples.observe.agents.analyst import AnalystAgent
    from atrium.examples.observe.agents.deep_diver import DeepDiverAgent
    for a in [PathfinderAgent, MapperAgent, AnalystAgent, DeepDiverAgent]:
        print(f"  {a.name:20s} {a.description}")


def cmd_agents_seed(args):
    """Seed agents from the built-in corpus (or a custom source directory)."""
    from atrium.core.agent_store import AgentStore
    from atrium.seeds import iter_seeds

    db_path = getattr(args, "db", "atrium_agents.db")
    store = AgentStore(db_path=db_path)

    source = getattr(args, "source", None)
    category_filter = getattr(args, "category", None)
    force = getattr(args, "force", False)

    seeds = iter_seeds(source=source)
    if category_filter:
        seeds = (s for s in seeds if s.get("category") == category_filter)

    if not force:
        # Default path: skip existing agents via seed_if_empty
        count = store.seed_if_empty(seeds)
        if count:
            print(f"Seeded {count} agent(s).")
        else:
            print("Store already populated — nothing seeded (use --force to overwrite).")
        return

    # --force: upsert every seed regardless of current store contents
    from atrium.api.routes.agent_builder import CreateAgentRequest
    from pydantic import ValidationError

    created = replaced = failed = 0
    for raw in seeds:
        name = raw.get("name", "<unknown>")
        try:
            req = CreateAgentRequest.model_validate(raw)
        except (ValidationError, Exception) as exc:
            print(f"  SKIP (invalid) {name}: {exc}")
            failed += 1
            continue

        existing = store.load(name)
        store.save(req.model_dump())
        if existing:
            print(f"  REPLACE {name}")
            replaced += 1
        else:
            print(f"  SEED {name}")
            created += 1

    print(f"Done. Seeded {created}, replaced {replaced}, skipped (invalid) {failed}.")


def cmd_worker(args):
    """Run a background worker."""
    import asyncio
    
    if args.name == "webhook-delivery":
        async def _run():
            from atrium.streaming.webhooks import WebhookStore, WebhookDeliveryWorker
            from atrium.streaming.events import EventRecorder
            import logging
            logging.basicConfig(level=logging.INFO)
            
            # Create store but open EventRecorder to share DB
            recorder = EventRecorder(db_path=args.db_path)
            await recorder.open()
            # The WebhookStore creates its own connection to the same DB
            store = WebhookStore(db_path=args.db_path)
            await store.open()
            
            worker = WebhookDeliveryWorker(store=store, poll_interval=2.0, recorder=recorder)
            worker.start()
            print("Webhook delivery worker started. Press Ctrl+C to stop.")
            try:
                while True:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass
            except KeyboardInterrupt:
                pass
            finally:
                await worker.stop()
                await store.close()
                await recorder.close()
                
        try:
            asyncio.run(_run())
        except KeyboardInterrupt:
            print("\nWorker stopped.")
    else:
        print(f"Unknown worker: {args.name}")
        sys.exit(1)


def cmd_new_agent(args):
    name = args.name
    class_name = "".join(word.capitalize() for word in name.split("_")) + "Agent"

    agent_code = f'''from atrium import Agent


class {class_name}(Agent):
    name = "{name}"
    description = ""  # TODO: Describe what this agent does
    capabilities = []  # TODO: Add capability tags

    # Optional: declare schemas for better Commander planning
    # input_schema = {{"key": type}}
    # output_schema = {{"key": type}}

    async def run(self, input_data: dict) -> dict:
        # TODO: Implement your agent logic
        await self.say("Starting work...")

        result = {{}}

        await self.say("Done")
        return result
'''

    test_code = f'''import pytest
from agents.{name} import {class_name}


@pytest.mark.asyncio
async def test_{name}_runs():
    agent = {class_name}()
    result = await agent.run({{}})
    assert isinstance(result, dict)
'''

    agent_dir = Path("agents")
    test_dir = Path("tests")
    agent_dir.mkdir(exist_ok=True)
    test_dir.mkdir(exist_ok=True)

    agent_file = agent_dir / f"{name}.py"
    test_file = test_dir / f"test_{name}.py"

    if agent_file.exists():
        print(f"Error: {agent_file} already exists")
        sys.exit(1)

    agent_file.write_text(agent_code)
    test_file.write_text(test_code)
    print(f"Created {agent_file}")
    print(f"Created {test_file}")
    print(f"Next: edit {agent_file}, then register it in your app.py")


def main():
    parser = argparse.ArgumentParser(prog="atrium", description="Atrium agent orchestration")
    sub = parser.add_subparsers(dest="command")

    serve_p = sub.add_parser("serve", help="Start the API + dashboard")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8080)
    serve_p.add_argument("--llm", default=None, help="LLM config (e.g. gemini:gemini-2.0-flash). Auto-detects from API keys if not set.")
    serve_p.set_defaults(func=cmd_serve)

    ver_p = sub.add_parser("version", help="Print version")
    ver_p.set_defaults(func=cmd_version)

    new_p = sub.add_parser("new", help="Scaffold new components")
    new_sub = new_p.add_subparsers(dest="new_type")
    agent_p = new_sub.add_parser("agent", help="Create a new agent")
    agent_p.add_argument("name", help="Agent name (snake_case)")
    agent_p.set_defaults(func=cmd_new_agent)

    # example run
    example_p = sub.add_parser("example", help="Run bundled examples")
    example_sub = example_p.add_subparsers(dest="example_action")
    run_p = example_sub.add_parser("run", help="Run an example")
    run_p.add_argument("name", help="Example name (hello_world, observe)")
    run_p.set_defaults(func=cmd_example_run)

    # agents list / seed
    agents_p = sub.add_parser("agents", help="Agent operations")
    agents_sub = agents_p.add_subparsers(dest="agents_action")

    list_p = agents_sub.add_parser("list", help="List available agents")
    list_p.set_defaults(func=cmd_agents_list)

    seed_p = agents_sub.add_parser("seed", help="Seed agents from the built-in corpus")
    seed_p.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Replace existing agents (upsert); default is skip-if-exists",
    )
    seed_p.add_argument(
        "--category",
        default=None,
        metavar="CAT",
        help="Only seed agents whose category matches CAT",
    )
    seed_p.add_argument(
        "--source",
        default=None,
        metavar="PATH",
        help="Load seed JSON files from PATH instead of the built-in corpus",
    )
    seed_p.add_argument(
        "--db",
        default="atrium_agents.db",
        metavar="PATH",
        help="SQLite database path (default: atrium_agents.db)",
    )
    seed_p.set_defaults(func=cmd_agents_seed)

    # Worker
    worker_p = sub.add_parser("worker", help="Run a background worker")
    worker_p.add_argument("name", choices=["webhook-delivery"], help="Worker to run")
    worker_p.add_argument("--db-path", default="atrium_events.db", help="Path to events DB")
    worker_p.set_defaults(func=cmd_worker)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
