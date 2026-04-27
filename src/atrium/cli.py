"""Atrium CLI — serve, scaffold, and run examples."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path


def cmd_serve(args):
    import uvicorn
    from atrium.api.app import create_app
    from atrium.core.registry import AgentRegistry
    app = create_app(registry=AgentRegistry(), llm_config=args.llm)
    print(f"Atrium serving at http://{args.host}:{args.port}")
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
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8080)
    serve_p.add_argument("--llm", default="openai:gpt-4o-mini")
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

    # agents list
    agents_p = sub.add_parser("agents", help="Agent operations")
    agents_sub = agents_p.add_subparsers(dest="agents_action")
    list_p = agents_sub.add_parser("list", help="List available agents")
    list_p.set_defaults(func=cmd_agents_list)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
