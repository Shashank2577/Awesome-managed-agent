# Seeding Agents

Atrium ships with 185+ pre-built agents across 11 categories. This guide explains the seed corpus, the JSON format, and how to extend it.

## What is the seed corpus?

The seed corpus is a collection of JSON agent definitions bundled with Atrium at `src/atrium/seeds/agents/<category>/<slug>.json`. On a fresh install, these definitions are loaded into the `agent_configs` SQLite table once at boot. They cover HTTP API wrappers and LLM expert personas across 11 categories: `research`, `coding`, `writing`, `security`, `data`, `ops`, `design`, `communication`, `analysis`, `creative`, and `productivity`.

## Seed JSON format

### HTTP agent

```json
{
  "name": "seed/datamuse-words",
  "description": "Find words related in meaning, rhyme, or context to a given word using the Datamuse API.",
  "agent_type": "http",
  "category": "analysis",
  "api_url": "https://api.datamuse.com/words",
  "method": "GET",
  "headers": {},
  "query_params": {
    "ml": "{query}",
    "max": "20"
  },
  "response_path": "",
  "capabilities": ["words", "rhyme", "synonyms", "language", "linguistics"],
  "seeded": true,
  "seed_version": 1
}
```

### LLM agent

```json
{
  "name": "seed/error-detective",
  "description": "Search logs and codebases for error patterns, stack traces, and anomalies.",
  "agent_type": "llm",
  "category": "analysis",
  "system_prompt": "You are an error detective specializing in log analysis and pattern recognition...",
  "model": "anthropic:claude-sonnet-4-6",
  "capabilities": ["log_analysis", "debugging", "error_detection"],
  "seeded": true,
  "seed_version": 1
}
```

## Naming convention

- `name`: `seed/<slug>` — the `seed/` prefix distinguishes corpus agents from user-created ones.
- File path: `src/atrium/seeds/agents/<category>/<slug>.json`
- `slug` should be lowercase, hyphen-separated, and match the filename (e.g. `error-detective` → `error-detective.json`).

## How seeding works at boot

`seed_if_empty()` runs once when Atrium starts. It checks whether `agent_configs` is empty. If so, it reads every JSON file under `src/atrium/seeds/agents/`, calls `POST /agents/bulk` with `mode="skip"`, and logs the count. On subsequent starts (when the DB already has agents), it does nothing — user changes are never overwritten.

## CLI commands

```bash
# Seed agents from the built-in corpus (runs seed_if_empty logic)
atrium agents seed

# Force re-seed even if agents already exist (resets user edits to seeded agents)
atrium agents seed --force

# Seed only one category
atrium agents seed --category coding

# Seed from a custom directory
atrium agents seed --source /path/to/custom/agents/
```

## Adding a new seed agent

1. Create the JSON file at `src/atrium/seeds/agents/<category>/<slug>.json`. Follow the format above. Set `"seeded": true` and `"seed_version": 1`.

2. Validate with the test suite:

   ```bash
   pytest tests/test_core/test_seeds.py -v
   ```

   The test suite checks: valid JSON, required fields present, `name` matches `seed/<slug>`, `category` matches the directory name, no duplicate names across the corpus.

3. Commit the file. The seed appears on the next fresh install or `atrium agents seed --force` run.

## Idempotency

`seed_if_empty` is safe to call multiple times — it only writes when the store is empty. Agents created by users are never touched. Use `--force` to reset seeded agents to their corpus definitions (user-created agents with non-`seed/` names are unaffected).

## Import scripts

`scripts/import_wshobson.py` converts Markdown agent definitions (from the [wshobson/agents](https://github.com/wshobson/agents) format) into Atrium seed JSON. Re-run it when the upstream repo is updated:

```bash
# Clone upstream, then run the importer
git clone https://github.com/wshobson/agents /tmp/wshobson-agents
python3 scripts/import_wshobson.py --source /tmp/wshobson-agents

# Review the diff, run tests, then commit
git diff src/atrium/seeds/
pytest tests/test_core/test_seeds.py
```
