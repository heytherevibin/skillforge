# Changelog

## 0.2.0

- **`skillforge route`**: CLI parity with MCP **`route_skills`** (same `build_router_and_skills` + `run_route_turn` pipeline); optional **`--project-root`**, **`--session-id`**, **`--user-id`**, **`--json-meta`**.
- **`app.db_paths`**: **`global_db_path`** / **`resolve_orchestrator_db`** extracted for lightweight tests and reuse.
- **MCP**: **`MCPServer.setup`** now uses **`build_router_and_skills`** (single router construction path with the CLI).
- **CI**: **`pytest`** over **`python/tests/`** (no full ML install for DB path tests); **`py_compile`** includes **`db_paths.py`** and **`route_cli.py`**.

## 0.1.0

Initial public npm release: MCP stdio server, optional HTTP API, bundled skill catalog, per-project **`.skillforge/orchestrator.db`**, **`skillforge events`**, learning loop.
