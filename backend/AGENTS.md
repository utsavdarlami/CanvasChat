# Agent Notes

- Before running any Python script or test command, activate the project virtual environment first: `source .venv/bin/activate`.

## Checking Installed Packages

To check installed package versions:

```bash
source .venv/bin/activate
uv pip freeze | rg <package_name>
```

Example: `uv pip freeze | rg google` shows all Google-related packages.

## ADK State vs LLM Visibility

The Google ADK session state (`tool_context.state`) is a **Python-side data store**. Only tool functions can read it. The LLM agent itself only sees: the system instruction, conversation messages, and tool return values. It cannot "reach into" session state.

**Implication:** If the LLM needs to know something (e.g., which entities are selected), it must be either:
1. Injected into the query/message text (preferred for per-request context like selection)
2. Returned by a tool the LLM calls
3. Templated into the instruction (if ADK supports it)

Simply writing data to `state_delta` makes it available to tools but **invisible to the LLM**.
