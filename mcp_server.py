#!/usr/bin/env python3
"""
Agent Graph Memory — MCP Server
Shared knowledge graph for Claude + Gemini collaboration.

Transports:
  SSE (default):  http://localhost:3333/sse
  stdio:          docker exec -i agent-graph-mcp python3 mcp_server.py
"""
import asyncio
import os
import json
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP

# ── Config ────────────────────────────────────────────────────────────────────

SURREALDB_URL  = os.getenv("SURREALDB_URL",  "ws://surrealdb:8000/rpc")
SURREALDB_USER = os.getenv("SURREALDB_USER", "root")
SURREALDB_PASS = os.getenv("SURREALDB_PASS", "root_password")
SURREALDB_NS   = os.getenv("SURREALDB_NS",   "project")
SURREALDB_DB   = os.getenv("SURREALDB_DB",   "main")
MCP_TRANSPORT  = os.getenv("MCP_TRANSPORT",  "sse")
MCP_HOST       = os.getenv("MCP_HOST",       "0.0.0.0")
MCP_PORT       = int(os.getenv("MCP_PORT",   "3333"))

mcp = FastMCP("AgentGraph", host=MCP_HOST, port=MCP_PORT)

# ── DB connection (singleton with auto-reconnect) ─────────────────────────────

_db = None

async def db():
    global _db
    if _db is None:
        from surrealdb import AsyncSurreal
        _db = AsyncSurreal(SURREALDB_URL)
        await _db.connect()
        await _db.signin({"username": SURREALDB_USER, "password": SURREALDB_PASS})
        await _db.use(SURREALDB_NS, SURREALDB_DB)
    return _db

async def q(query: str, vars: dict = None) -> list:
    """Execute a SurrealQL query and return result rows."""
    conn = await db()
    result = await conn.query(query, vars or {})
    if isinstance(result, list):
        return result
    return []

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# ═══════════════════════════════════════════════════════════════════════════════
# NAVIGATION TOOLS — find code locations without reading files
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def find_handler(endpoint: str) -> str:
    """
    Find handler file + line for an API endpoint.
    Example: find_handler('/api/users/:id')
    Saves reading 3-4 files to locate the handler.
    """
    rows = await q(
        "SELECT path, method, file, line, handler_fn, spec FROM endpoint WHERE path = $path",
        {"path": endpoint}
    )
    if not rows:
        rows = await q(
            "SELECT path, method, file, line, handler_fn, spec FROM endpoint WHERE path CONTAINS $part",
            {"part": endpoint.strip("/")}
        )
    if not rows:
        return f"Endpoint '{endpoint}' not indexed. Run indexer.py or try list_endpoints()."

    out = []
    for r in rows:
        out.append(
            f"{r['method']:6} {r['path']}\n"
            f"  File:    {r['file']}:{r.get('line', '?')}\n"
            f"  Handler: {r.get('handler_fn', '—')}\n"
            f"  Spec:    {r.get('spec', '—')}"
        )
    return "\n\n".join(out)


@mcp.tool()
async def list_endpoints(prefix: str = "") -> str:
    """
    List all indexed API endpoints, optionally filtered by URL prefix.
    Example: list_endpoints('/api/users')
    """
    if prefix:
        rows = await q(
            "SELECT method, path, file, spec FROM endpoint WHERE path CONTAINS $p ORDER BY path",
            {"p": prefix}
        )
    else:
        rows = await q("SELECT method, path, file, spec FROM endpoint ORDER BY path")

    if not rows:
        return "No endpoints indexed. Run: docker exec agent-graph-mcp python3 /app/indexer.py"

    lines = [f"{r['method']:6} {r['path']:<48} {r.get('file', '')}"]
    return "\n".join(lines)


@mcp.tool()
async def find_component(name: str) -> str:
    """
    Find React component location and what hooks/API calls it uses.
    Example: find_component('UserPage')
    """
    rows = await q(
        "SELECT name, file, hooks, api_calls FROM component WHERE name = $name",
        {"name": name}
    )
    if not rows:
        # Fallback: search TypeScript types (interface/type/enum)
        ts_rows = await q(
            "SELECT name, kind, file, fields FROM tstype WHERE name = $name",
            {"name": name}
        )
        if ts_rows:
            r = ts_rows[0]
            return (
                f"TypeScript {r['kind']}: {r['name']}\n"
                f"File:   {r['file']}\n"
                f"Fields: {', '.join(r.get('fields') or []) or 'none'}"
            )
        # Partial match across components and types
        similar = await q(
            "SELECT name, file FROM component WHERE name CONTAINS $part",
            {"part": name}
        )
        ts_similar = await q(
            "SELECT name, kind, file FROM tstype WHERE name CONTAINS $part",
            {"part": name}
        )
        found = [r["name"] for r in similar] + [f"{r['name']} ({r['kind']})" for r in ts_similar]
        if found:
            return f"Exact match not found. Similar: {', '.join(found)}"
        return f"Component or type '{name}' not indexed."

    r = rows[0]
    hooks = r.get("hooks") or []
    apis  = r.get("api_calls") or []
    return (
        f"Component: {r['name']}\n"
        f"File:      {r['file']}\n"
        f"Hooks:     {', '.join(hooks) or 'none'}\n"
        f"API calls: {', '.join(apis) or 'none'}"
    )


@mcp.tool()
async def what_uses(symbol: str) -> str:
    """
    Find all components/handlers that import or call a given symbol.
    Example: what_uses('useUsers') or what_uses('UserHandler')
    Useful to understand blast radius before changing something.
    """
    rows = await q(
        """SELECT
             array::group(<-uses<-component.name) AS used_by_components,
             array::group(<-calls<-handler.handler_fn) AS called_by_handlers,
             array::group(<-imports<-file.path) AS imported_in
           FROM (SELECT id FROM hook, api_fn, handler_fn WHERE name = $sym)""",
        {"sym": symbol}
    )
    if not rows or not any(rows[0].values()):
        return f"'{symbol}' not found in index. May not be indexed yet."

    r = rows[0]
    return (
        f"Symbol: {symbol}\n"
        f"Used by components:  {', '.join(r.get('used_by_components') or []) or 'none'}\n"
        f"Called by handlers:  {', '.join(r.get('called_by_handlers') or []) or 'none'}\n"
        f"Imported in files:   {', '.join(r.get('imported_in') or []) or 'none'}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SPEC TOOLS — task status without reading INDEX.md
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_spec(ticket: str) -> str:
    """
    Get full spec info for a ticket: status, AC, key files, branch.
    Example: get_spec('AUTH-01')
    """
    rows = await q(
        "SELECT * FROM spec WHERE ticket = $t",
        {"t": ticket.upper()}
    )
    if not rows:
        return f"Spec '{ticket}' not found. Run indexer.py to index specs."

    r = rows[0]
    ac_lines = "\n".join(
        f"  {'✅' if a.get('done') else '❌'} {a['text']}"
        for a in (r.get("ac") or [])
    ) or "  (no AC indexed)"

    return (
        f"Ticket: {r['ticket']} [{r['status'].upper()}]\n"
        f"Branch: {r.get('branch', '—')}\n"
        f"Spec:   {r.get('spec_path', '—')}\n"
        f"Files:\n  " + "\n  ".join(r.get("key_files") or ["none"]) +
        f"\nAC:\n{ac_lines}"
    )


@mcp.tool()
async def list_specs(status: str = "") -> str:
    """
    List all specs, optionally filtered by status: ready|in-progress|done|draft
    Example: list_specs('ready') — show what's next to implement
    """
    if status:
        rows = await q(
            "SELECT ticket, status, spec_path FROM spec WHERE status = $s ORDER BY ticket",
            {"s": status}
        )
    else:
        rows = await q("SELECT ticket, status, spec_path FROM spec ORDER BY status, ticket")

    if not rows:
        return "No specs indexed."

    by_status: dict = {}
    for r in rows:
        by_status.setdefault(r["status"], []).append(r["ticket"])

    lines = []
    for s, tickets in sorted(by_status.items()):
        lines.append(f"[{s}] " + ", ".join(tickets))
    return "\n".join(lines)


@mcp.tool()
async def update_spec_status(ticket: str, status: str, agent: str = "claude") -> str:
    """
    Update spec status in the graph.
    status: ready | in-progress | done | rejected
    agent: claude | gemini
    """
    valid = {"ready", "in-progress", "done", "rejected", "draft"}
    if status not in valid:
        return f"Invalid status '{status}'. Use: {', '.join(valid)}"

    rows = await q(
        "UPDATE spec SET status = $s, updated_by = $a, updated_at = $t WHERE ticket = $ticket RETURN AFTER",
        {"ticket": ticket.upper(), "s": status, "a": agent, "t": now_iso()}
    )
    if not rows:
        return f"Spec '{ticket}' not found."
    return f"✅ {ticket} → {status} (updated by {agent})"


# ═══════════════════════════════════════════════════════════════════════════════
# MULTI-AGENT COLLABORATION TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def leave_note(to_agent: str, topic: str, content: str, from_agent: str = "claude") -> str:
    """
    Leave a note for the other agent.
    to_agent: 'gemini' or 'claude'
    Example: leave_note('gemini', 'AUTH-01', 'Done, check the Helm values')
    """
    await q(
        """CREATE note SET
           to_agent = $to, from_agent = $from,
           topic = $topic, content = $content,
           created_at = $t, read = false""",
        {"to": to_agent, "from": from_agent, "topic": topic,
         "content": content, "t": now_iso()}
    )
    return f"📝 Note left for {to_agent} on topic '{topic}'"


@mcp.tool()
async def read_notes(agent: str = "claude") -> str:
    """
    Read unread notes addressed to this agent.
    Example: read_notes('claude')
    """
    rows = await q(
        "SELECT id, from_agent, topic, content, created_at FROM note WHERE to_agent = $a AND read = false ORDER BY created_at DESC",
        {"a": agent}
    )
    if not rows:
        return f"No unread notes for {agent}."

    ids = [r["id"] for r in rows]
    await q("UPDATE note SET read = true WHERE id IN $ids", {"ids": ids})

    lines = []
    for r in rows:
        lines.append(
            f"From {r['from_agent']} [{r['created_at'][:16]}] — {r['topic']}\n"
            f"  {r['content']}"
        )
    return f"📬 {len(rows)} note(s) for {agent}:\n\n" + "\n\n".join(lines)


@mcp.tool()
async def log_decision(topic: str, decision: str, rationale: str, agent: str = "claude") -> str:
    """
    Log an architectural or implementation decision to shared memory.
    Both agents can read this to stay aligned.
    Example: log_decision('auth', 'Use JWT not sessions', 'Stateless for k8s')
    """
    await q(
        """CREATE decision SET
           topic = $topic, decision = $dec,
           rationale = $rat, agent = $agent,
           created_at = $t""",
        {"topic": topic, "dec": decision, "rat": rationale,
         "agent": agent, "t": now_iso()}
    )
    return f"✅ Decision logged: [{topic}] {decision}"


@mcp.tool()
async def get_decisions(topic: str = "") -> str:
    """
    Get logged decisions, optionally filtered by topic.
    Useful at session start to understand past choices.
    """
    if topic:
        rows = await q(
            "SELECT topic, decision, rationale, agent, created_at FROM decision WHERE topic CONTAINS $t ORDER BY created_at DESC LIMIT 20",
            {"t": topic}
        )
    else:
        rows = await q(
            "SELECT topic, decision, rationale, agent, created_at FROM decision ORDER BY created_at DESC LIMIT 20"
        )

    if not rows:
        return "No decisions logged yet."

    lines = []
    for r in rows:
        lines.append(
            f"[{r['topic']}] {r['decision']}\n"
            f"  Why: {r['rationale']}\n"
            f"  By: {r['agent']} at {r['created_at'][:16]}"
        )
    return "\n\n".join(lines)


@mcp.tool()
async def claim_task(ticket: str, agent: str, note: str = "") -> str:
    """
    Claim a task to prevent double work between agents.
    Example: claim_task('AUTH-01', 'gemini', 'Working on JWT middleware')
    """
    existing = await q(
        "SELECT agent, note, claimed_at FROM task_claim WHERE ticket = $t AND status = 'active'",
        {"t": ticket.upper()}
    )
    if existing:
        r = existing[0]
        return f"⚠️ {ticket} already claimed by {r['agent']} at {r['claimed_at'][:16]}: {r.get('note', '')}"

    await q(
        """CREATE task_claim SET
           ticket = $t, agent = $agent, note = $note,
           claimed_at = $ts, status = 'active'""",
        {"t": ticket.upper(), "agent": agent, "note": note, "ts": now_iso()}
    )
    return f"🔒 {ticket} claimed by {agent}"


@mcp.tool()
async def release_task(ticket: str, agent: str) -> str:
    """Release a claimed task when done."""
    await q(
        "UPDATE task_claim SET status = 'released', released_at = $ts WHERE ticket = $t AND agent = $a AND status = 'active'",
        {"t": ticket.upper(), "a": agent, "ts": now_iso()}
    )
    return f"🔓 {ticket} released by {agent}"


@mcp.tool()
async def active_tasks() -> str:
    """Show all currently claimed tasks."""
    rows = await q(
        "SELECT ticket, agent, note, claimed_at FROM task_claim WHERE status = 'active' ORDER BY claimed_at"
    )
    if not rows:
        return "No active task claims."
    lines = [f"  {r['ticket']:20} → {r['agent']:8} [{r['claimed_at'][:16]}] {r.get('note', '')}"
             for r in rows]
    return "Active claims:\n" + "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT MEMORY — quick access to facts without reading files
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def remember(key: str, value: str, agent: str = "claude") -> str:
    """
    Store a fact in shared project memory.
    Example: remember('db_host', 'postgres:5432', 'claude')
    """
    await q(
        """INSERT INTO kv_store (key, val, agent, updated_at)
           VALUES ($key, $value, $agent, $t)
           ON DUPLICATE KEY UPDATE val = $value, agent = $agent, updated_at = $t""",
        {"key": key, "value": value, "agent": agent, "t": now_iso()}
    )
    return f"💾 Remembered: {key}"


@mcp.tool()
async def recall(key: str) -> str:
    """
    Retrieve a stored fact.
    Example: recall('db_host')
    """
    rows = await q(
        "SELECT val, agent, updated_at FROM kv_store WHERE key = $key",
        {"key": key}
    )
    if not rows:
        rows = await q(
            "SELECT key, val FROM kv_store WHERE key CONTAINS $key LIMIT 5",
            {"key": key}
        )
        if rows:
            found = "\n".join(f"  {r['key']}: {r['val'][:60]}" for r in rows)
            return f"Key '{key}' not found. Similar:\n{found}"
        return f"Nothing stored for '{key}'"

    r = rows[0]
    return f"{key} = {r['val']}\n(stored by {r['agent']} at {r['updated_at'][:16]})"


@mcp.tool()
async def get_module_context(module: str) -> str:
    """
    Get everything known about a module: specs, endpoints, components, decisions.
    Example: get_module_context('auth') or get_module_context('payments')
    Perfect for session start — replaces reading multiple files.
    """
    mod = module.lower()

    specs = await q(
        "SELECT ticket, status FROM spec WHERE string::lowercase(ticket) CONTAINS $m ORDER BY ticket",
        {"m": mod}
    )
    endpoints = await q(
        "SELECT method, path FROM endpoint WHERE path CONTAINS $m ORDER BY path",
        {"m": mod}
    )
    components = await q(
        "SELECT name, file FROM component WHERE string::lowercase(name) CONTAINS $m",
        {"m": mod}
    )
    decisions = await q(
        "SELECT topic, decision, agent FROM decision WHERE string::lowercase(topic) CONTAINS $m ORDER BY created_at DESC LIMIT 5",
        {"m": mod}
    )

    lines = [f"=== Module: {module} ===\n"]

    if specs:
        lines.append("Specs: " + ", ".join(f"{r['ticket']}[{r['status']}]" for r in specs))
    if endpoints:
        lines.append("Endpoints:\n" + "\n".join(f"  {r['method']:6} {r['path']}" for r in endpoints))
    if components:
        lines.append("Components:\n" + "\n".join(f"  {r['name']} ({r['file']})" for r in components))
    if decisions:
        lines.append("Decisions:\n" + "\n".join(f"  [{r['topic']}] {r['decision']}" for r in decisions))

    if len(lines) == 1:
        return f"Module '{module}' not found in graph. Run indexer.py first."

    return "\n\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT CONTEXT — indexed context file without reading it
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_project_context(section: str = "") -> str:
    """
    Get project context from indexed context file (CLAUDE.md / AGENTS.md).
    section: mission | architecture | module | contract | constant | commands | "" (all)
    Example: get_project_context('module') — list all modules with status
    Replaces reading your context file at session start.
    """
    if section:
        rows = await q(
            "SELECT section, key, content, status, comment FROM context WHERE section = $s ORDER BY key",
            {"s": section}
        )
    else:
        rows = await q(
            "SELECT section, key, content, status, comment FROM context ORDER BY section, key"
        )

    if not rows:
        return "No context indexed. Run: docker exec agent-graph-mcp python3 /app/indexer.py"

    by_section: dict = {}
    for r in rows:
        by_section.setdefault(r["section"], []).append(r)

    lines = []
    for sec, items in sorted(by_section.items()):
        lines.append(f"=== {sec.upper()} ===")
        for r in items:
            if sec == "module":
                lines.append(f"  [{r.get('status','?')}] {r['key']}: {r['content']}")
            elif sec == "constant":
                lines.append(f"  {r['key']} = {r['content']}  // {r.get('comment','')}")
            elif sec in ("mission", "architecture", "commands"):
                lines.append(r["content"])
            else:
                lines.append(f"  {r['key']}: {r['content']}")

    return "\n\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def start_session(agent: str, task: str) -> str:
    """
    Start a new work session. Call at the beginning of each conversation.
    agent: 'claude' | 'gemini'
    task: brief description of what you're working on
    Example: start_session('claude', 'Implementing AUTH-01 login flow')
    """
    await q(
        """CREATE session SET
           agent=$agent, task=$task,
           started_at=$t, ended_at=NONE,
           files_touched=[], summary='', status='active'""",
        {"agent": agent, "task": task, "t": now_iso()}
    )
    last = await q(
        """SELECT task, summary, ended_at, started_at FROM session
           WHERE agent=$a AND status='done'
           ORDER BY started_at DESC LIMIT 1""",
        {"a": agent}
    )
    msg = f"🟢 Session started: {task}"
    if last:
        r = last[0]
        msg += f"\n\nLast session [{r.get('ended_at','?')[:16]}]: {r.get('task','')}"
        if r.get("summary"):
            msg += f"\n  Summary: {r['summary']}"
    return msg


@mcp.tool()
async def update_session(agent: str, files_touched: list, summary: str = "") -> str:
    """
    Update current session with progress. Call when switching tasks or touching key files.
    files_touched: list of file paths modified in this session
    summary: what was done so far (optional, cumulative)
    Example: update_session('claude', ['src/api/handlers/auth.go'], 'Handler skeleton done')
    """
    rows = await q(
        "SELECT id, files_touched, started_at FROM session WHERE agent=$a AND status='active' ORDER BY started_at DESC LIMIT 1",
        {"a": agent}
    )
    if not rows:
        return f"No active session for {agent}. Call start_session() first."

    session_id = rows[0]["id"]
    existing = rows[0].get("files_touched") or []
    merged = list(dict.fromkeys(existing + files_touched))

    update_q = "UPDATE $id SET files_touched=$files"
    params = {"id": session_id, "files": merged}
    if summary:
        update_q += ", summary=$summary"
        params["summary"] = summary

    await q(update_q, params)
    return f"✅ Session updated — {len(merged)} file(s) tracked"


@mcp.tool()
async def end_session(agent: str, summary: str) -> str:
    """
    End current session with a final summary. Call at conversation end.
    summary: what was accomplished, what's left, any blockers
    Example: end_session('claude', 'AUTH-01 done: handler + routes. Tests pending.')
    """
    rows = await q(
        "SELECT id, started_at FROM session WHERE agent=$a AND status='active' ORDER BY started_at DESC LIMIT 1",
        {"a": agent}
    )
    if not rows:
        return f"No active session for {agent}."

    await q(
        "UPDATE $id SET status='done', summary=$s, ended_at=$t",
        {"id": rows[0]["id"], "s": summary, "t": now_iso()}
    )
    return f"🔴 Session ended. Summary saved."


@mcp.tool()
async def get_last_session(agent: str = "") -> str:
    """
    Get the last session(s) to resume context.
    Call at conversation start to know where things left off.
    agent: 'claude' | 'gemini' | '' (both)
    """
    if agent:
        rows = await q(
            """SELECT agent, task, summary, files_touched, started_at, ended_at, status
               FROM session WHERE agent=$a ORDER BY started_at DESC LIMIT 3""",
            {"a": agent}
        )
    else:
        rows = await q(
            """SELECT agent, task, summary, files_touched, started_at, ended_at, status
               FROM session ORDER BY started_at DESC LIMIT 5"""
        )

    if not rows:
        return "No sessions recorded yet."

    lines = []
    for r in rows:
        status = "🟢 ACTIVE" if r["status"] == "active" else "🔴 done"
        started = (r.get("started_at") or "")[:16]
        ended   = (r.get("ended_at") or "—")[:16]
        files   = r.get("files_touched") or []
        lines.append(
            f"{status} [{r['agent']}] {r['task']}\n"
            f"  Started: {started}  Ended: {ended}\n"
            f"  Files:   {', '.join(files[:5]) or 'none'}{' ...' if len(files) > 5 else ''}\n"
            f"  Summary: {r.get('summary') or '—'}"
        )
    return "\n\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE INDEX TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_service(name: str = "") -> str:
    """
    Get service info (directory, status) indexed from specs/INDEX.md.
    Example: get_service('api') or get_service() for all services.
    """
    if name:
        rows = await q(
            "SELECT name, directory, status FROM service WHERE name = $n",
            {"n": name}
        )
        if not rows:
            rows = await q(
                "SELECT name, directory, status FROM service WHERE name CONTAINS $n",
                {"n": name}
            )
    else:
        rows = await q("SELECT name, directory, status FROM service ORDER BY name")

    if not rows:
        return "No services indexed. Run: docker exec agent-graph-mcp python3 /app/indexer.py"

    lines = []
    for r in rows:
        lines.append(f"  {r['name']:<20} {r['directory']:<30} {r['status']}")
    return "Services:\n" + "\n".join(lines)


@mcp.tool()
async def get_history(limit: int = 10, ticket: str = "") -> str:
    """
    Get implementation history from specs/INDEX.md (chronological order).
    limit: how many recent entries to return (default 10)
    ticket: filter by specific ticket name (optional)
    Example: get_history(5) — last 5 implemented specs
    """
    if ticket:
        rows = await q(
            "SELECT order, ticket, description FROM history WHERE ticket CONTAINS $t ORDER BY order DESC LIMIT $l",
            {"t": ticket.upper(), "l": limit}
        )
    else:
        rows = await q(
            "SELECT order, ticket, description FROM history ORDER BY order DESC LIMIT $l",
            {"l": limit}
        )

    if not rows:
        return "No history indexed. Run: docker exec agent-graph-mcp python3 /app/indexer.py"

    lines = [f"  #{r['order']:>3}  {r['ticket']:<35} {r['description'][:70]}" for r in rows]
    return f"Implementation history (last {len(rows)}):\n" + "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRYPOINT — dual transport: SSE (GET /sse) + Streamable HTTP (POST /mcp)
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    transport = MCP_TRANSPORT if MCP_TRANSPORT in ("sse", "stdio") else "sse"

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Mount

        sse_app = mcp.sse_app()
        http_app = mcp.streamable_http_app()

        combined_routes = list(http_app.routes) + list(sse_app.routes)
        http_lifespan = http_app.router.lifespan_context
        app = Starlette(routes=combined_routes, lifespan=http_lifespan)

        print(f"🚀 MCP server starting on {MCP_HOST}:{MCP_PORT}")
        print(f"   SSE transport:              GET  http://{MCP_HOST}:{MCP_PORT}/sse")
        print(f"   Streamable HTTP transport:  POST http://{MCP_HOST}:{MCP_PORT}/mcp")

        uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)
