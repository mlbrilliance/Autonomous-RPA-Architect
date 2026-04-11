# Autonomous RPA Architect - Project Rules

## Required MCP Servers

The following MCP servers **must** be used in this project:

| MCP Server | Purpose | Tools |
|------------|---------|-------|
| **multi-model-router** | Route tasks to optimal models (Gemini, OpenRouter, Codex, etc.) | `analyze_requirements`, `consult_*`, `execute_routing_plan` |
| **claude-flow (ruflo)** | Multi-agent orchestration, workflows, browser automation, memory | `agent_spawn`, `swarm_init`, `workflow_*`, `browser_*`, `memory_*` |
| **tavily** | Web search, content extraction, deep research | `tavily-search`, `tavily-extract` |
| **exa** | Semantic web search, code context lookup | `web_search_exa`, `get_code_context_exa` |
| **Ref** | API and framework documentation lookup | `ref_search_documentation`, `ref_read_url` |

## Routing Rules

- Always use `mcp__multi-model-router__analyze_requirements` to score and route non-trivial tasks.
- Use `claude-flow` for any multi-agent coordination, workflow execution, or browser-based automation.
- Use `tavily` + `exa` for web research, library lookups, and current information.
- Use `Ref` to check documentation before implementing against any external API or framework.
- When tasks include `mcpTools` recommendations from the router, invoke them as prerequisites before executing.

## Multi-Model Deliberation (Required)

During coding, testing, debugging, and iterative improvement loops, **always** consult at least one OpenRouter model (`glm`, `minimax`, `deepseek`, or `qwen` via `consult_openrouter`) for code review, bug analysis, or alternative approaches. This is mandatory — different models catch different issues and provide diverse perspectives.
