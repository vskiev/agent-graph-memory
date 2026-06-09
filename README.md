# Agent Graph Memory

Shared knowledge graph for multi-agent collaborative development (Claude + Gemini or any two AI agents).
Reduces context usage ~10x by replacing file reads with targeted queries.

## How it works

An MCP server sits in front of SurrealDB and exposes tools that agents call instead of reading files.
Both agents connect to the **same** database via SSE — sessions, notes, decisions, and indexed code are all shared.

```
Claude Code ──┐
              ├── SSE :3333 ──► mcp_server.py ──► SurrealDB :8000
Gemini     ──┘                                        │
                                                 shared graph
                                    context · specs · endpoints · components
                                    sessions · notes · decisions · memory
```

---

## Quick Start

```bash
cd graph-memory

# 1. Start SurrealDB 2.6.5 + MCP server
docker compose up -d

# 2. Index your codebase (run after every merge)
docker exec <mcp_container> python3 /app/indexer.py

# 3. Connect Claude Code — add to ~/.claude/settings.json:
#    { "mcpServers": { "your-graph": { "type": "sse", "url": "http://localhost:3333/sse" } } }
```

## Connect Agents

### Claude Code
Copy `configs/claude_settings.json` into `~/.claude/settings.json` (or merge with existing).

### Gemini
Copy `configs/gemini_settings.json` into Gemini's MCP config.
See **[GEMINI.md](GEMINI.md)** for full Gemini setup and coordination protocol.

---

## Available Tools

### Project Context
| Tool | Description |
|------|-------------|
| `get_project_context('module')` | Indexed sections from your main context file (e.g. CLAUDE.md) |
| `get_project_context('architecture')` | Architecture section |
| `get_project_context('contract')` | Contract addresses / external endpoints |
| `get_project_context('commands')` | Quick-start commands |
| `get_module_context('payments')` | Full context for a named module in one call |

### Session State
| Tool | Description |
|------|-------------|
| `start_session('claude', 'Working on AUTH-01')` | Start of conversation — shows where you left off |
| `update_session('claude', ['handler.go'], 'Done login flow')` | Track files touched during work |
| `end_session('claude', 'AUTH-01 done, tests pending')` | Save summary at end of conversation |
| `get_last_session()` | See what Claude and Gemini did last |

### Code Navigation
| Tool | Replaces |
|------|---------|
| `find_handler('/api/auth/login')` | grep across handlers/ |
| `list_endpoints('/api/auth')` | reading main.go |
| `find_component('LoginPage')` | reading src/pages/ |
| `what_uses('useAuth')` | grep -r across the entire frontend |

### Specs
| Tool | Description |
|------|-------------|
| `get_spec('AUTH-01')` | Spec status, AC, branch, key files |
| `list_specs('ready')` | All specs available to pick up |
| `update_spec_status('AUTH-01', 'in-progress', 'claude')` | Move spec to new status |

### Multi-agent Collaboration
| Tool | Description |
|------|-------------|
| `leave_note('gemini', 'AUTH-01', 'Done, check the Helm values')` | Claude → Gemini message |
| `read_notes('claude')` | Read unread messages from other agents |
| `log_decision('auth', 'JWT not sessions', 'Stateless for k8s')` | Record architectural decision |
| `get_decisions('auth')` | Look up past decisions on a topic |
| `claim_task('AUTH-01', 'gemini')` | Signal that an agent is working on a ticket |
| `active_tasks()` | See who is working on what right now |
| `release_task('AUTH-01', 'gemini')` | Release claim when done |

### Project Memory
| Tool | Description |
|------|-------------|
| `remember('contract_addr', '0x1234...', 'claude')` | Store a key fact |
| `recall('contract_addr')` | Retrieve a stored fact |

---

## Recommended Session Flow

```
# Start of conversation:
start_session('claude', 'what you are working on')
get_last_session()              # see where the other agent left off
get_project_context('module')   # instead of reading your context file

# During work:
claim_task('TICKET-01', 'claude')
update_session('claude', ['path/to/file'], 'progress summary')

# End of conversation:
end_session('claude', 'what was done, what is left, any blockers')
leave_note('gemini', 'topic', 'message')   # if the other agent needs to know
release_task('TICKET-01', 'claude')
```

---

## What Gets Indexed

The `indexer.py` reads your repo and populates these tables:

| Table | Content |
|-------|---------|
| `context` | Sections from your main context file (CLAUDE.md / AGENTS.md) |
| `spec` | Task specs — status, acceptance criteria, branch, key files |
| `endpoint` | API routes with file path and handler name |
| `component` | Frontend components with hooks and API calls used |
| `hook` | Custom hooks |
| `service` | Top-level services / modules |
| `history` | Changelog / milestone entries |
| `decision` | Architectural decisions with rationale (from GEMINI.md) |
| `session` | Work sessions: agent, task, files touched, summary |
| `note` | Agent-to-agent messages |
| `memory` | Key-value facts (addresses, ports, flags, etc.) |

Adapt `indexer.py` to your repo structure — the parsing logic is straightforward and well-commented.

---

## Re-index After Merges

```bash
docker exec <mcp_container> python3 /app/indexer.py
```

Automate with a post-merge hook:

```bash
# .git/hooks/post-merge
#!/bin/bash
docker exec <mcp_container> python3 /app/indexer.py 2>/dev/null &
echo "Graph memory: reindexing in background..."
```

---

## Stack

| Component | Version | Role |
|-----------|---------|------|
| SurrealDB | **2.6.5** (pinned) | Graph database (RocksDB backend) |
| surrealdb Python SDK | 2.0.0 | DB client inside MCP server |
| Python MCP server | FastMCP | Exposes tools over SSE |
| Docker Compose | — | Single-command setup |

> **SurrealDB version note:** The Python SDK 2.0.0 officially claims compatibility with SurrealDB v2.0.0–v3.1.3.
> In practice, query parameters are silently dropped on v3.x (inserts produce empty rows).
> Pin to **v2.6.5** — it is fully compatible and stable.
