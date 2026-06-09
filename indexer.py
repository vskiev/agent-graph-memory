#!/usr/bin/env python3
"""
Agent Graph Indexer
Parses the repo and populates SurrealDB with the knowledge graph.

Run after merges:
  docker exec agent-graph-mcp python3 /app/indexer.py

Or locally (needs surrealdb pip package):
  SURREALDB_URL=ws://localhost:8000/rpc python3 indexer.py

--- CUSTOMIZE ---
This indexer is a template. Edit the parsers below to match your project structure.
Each function is independent — enable only what you need.
"""
import asyncio
import os
import re
from pathlib import Path

REPO        = Path(os.getenv("REPO_PATH", "/repo"))
DB_URL      = os.getenv("SURREALDB_URL",  "ws://surrealdb:8000/rpc")
DB_USER     = os.getenv("SURREALDB_USER", "root")
DB_PASS     = os.getenv("SURREALDB_PASS", "root_password")
DB_NS       = os.getenv("SURREALDB_NS",   "project")
DB_DB       = os.getenv("SURREALDB_DB",   "main")

# --- CUSTOMIZE: path to your Go API router file (relative to REPO root) ---
GO_MAIN_PATH = os.getenv("GO_MAIN_PATH", "api/cmd/server/main.go")

# --- CUSTOMIZE: path to your main context file ---
CONTEXT_FILE = os.getenv("CONTEXT_FILE", "CLAUDE.md")  # or AGENTS.md, README.md, etc.

# --- CUSTOMIZE: path to your secondary context file (infra/ops agent) ---
SECONDARY_CONTEXT_FILE = os.getenv("SECONDARY_CONTEXT_FILE", "GEMINI.md")


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> dict:
    """Extract | Key | Value | table from markdown."""
    data = {}
    for m in re.finditer(r'\|\s*(\w[\w\s]*?)\s*\|\s*(.+?)\s*\|', text):
        k = m.group(1).strip().lower()
        v = m.group(2).strip()
        if k not in ("field", "value", "---", ""):
            data[k] = v
    return data


def parse_ac(text: str) -> list[dict]:
    """Extract acceptance criteria from spec markdown."""
    items = []
    for m in re.finditer(r'- \[([ xX])\] \*\*?(AC-\d+)\*\*?:?\s*(.+)', text):
        items.append({
            "id":   m.group(2),
            "done": m.group(1).lower() == "x",
            "text": m.group(3).strip()
        })
    return items


def parse_key_files(text: str) -> list[str]:
    """Extract backtick-quoted file paths from a 'Key files' section."""
    files = []
    in_section = False
    for line in text.splitlines():
        # Matches common section headings in English or other languages
        if re.search(r'key files|ключові файли|ключевые файлы', line, re.I):
            in_section = True
            continue
        if in_section:
            if line.startswith("#"):
                break
            m = re.search(r'`([^`]+\.[a-z]{2,4})`', line)
            if m:
                files.append(m.group(1))
    return files


# ── Parsers ───────────────────────────────────────────────────────────────────

def index_context_file(repo: Path) -> list[dict]:
    """
    Parse your main context file (CLAUDE.md / AGENTS.md) → context records.

    --- CUSTOMIZE ---
    Edit the section headings below to match your context file structure.
    Each section becomes a queryable entry in the `context` table.
    """
    context_path = repo / CONTEXT_FILE
    if not context_path.exists():
        print(f"  ⚠ {CONTEXT_FILE} not found at {context_path}")
        return []

    text = context_path.read_text(encoding="utf-8")
    records = []

    def extract_section(heading: str) -> str:
        """Extract text from ## heading until next ##."""
        m = re.search(rf'^## {re.escape(heading)}(.+?)(?=^## |\Z)', text, re.MULTILINE | re.DOTALL)
        return m.group(1).strip() if m else ""

    # --- CUSTOMIZE: map your section headings to canonical section names ---
    # Format: ("Your ## heading text", "canonical_section_name", "key")
    TEXT_SECTIONS = [
        # ("Mission",        "mission",      "mission"),
        # ("Architecture",   "architecture", "overview"),
        # ("Quick Start",    "commands",     "quickstart"),
    ]

    for heading, section, key in TEXT_SECTIONS:
        content = extract_section(heading)
        if content:
            records.append({"section": section, "key": key, "content": content})

    # --- CUSTOMIZE: parse module/feature table ---
    # Uncomment and adapt if your context file has a module status table like:
    # **ModuleName** ✅ — description
    #
    # modules_text = extract_section("Modules")
    # for m in re.finditer(r'\*\*(\w+)\*\*\s*([✅]?)\s*[—-]\s*([^\n;]+)', modules_text):
    #     name, status_icon, desc = m.groups()
    #     records.append({
    #         "section": "module",
    #         "key":     name,
    #         "content": desc.strip(),
    #         "status":  "active" if "✅" in status_icon else "planned",
    #     })

    # --- CUSTOMIZE: parse constants table ---
    # Uncomment if you have a constants section like: CONST_NAME = 42  // description
    #
    # constants_text = extract_section("Constants")
    # for m in re.finditer(r'(\w+)\s*=\s*(\S+)\s*//\s*(.+)', constants_text):
    #     records.append({
    #         "section": "constant",
    #         "key":     m.group(1),
    #         "content": m.group(2),
    #         "comment": m.group(3).strip(),
    #     })

    print(f"  ✓ Indexed {len(records)} context records from {CONTEXT_FILE}")
    return records


def index_specs(repo: Path) -> list[dict]:
    """Parse specs/proj/PROJ-*.md → spec records."""
    records = []
    proj_dir = repo / "specs" / "proj"
    if not proj_dir.exists():
        print(f"  ⚠ specs/proj not found at {proj_dir}")
        return records

    for f in sorted(proj_dir.glob("PROJ-*.md")):
        text = f.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        ticket = f.stem.replace("PROJ-", "")

        records.append({
            "ticket":    ticket,
            "status":    fm.get("status", "unknown"),
            "branch":    fm.get("branch", ""),
            "spec_path": fm.get("spec", ""),
            "key_files": parse_key_files(text),
            "ac":        parse_ac(text),
        })

    print(f"  ✓ Indexed {len(records)} specs")
    return records


def index_go_routes(repo: Path) -> list[dict]:
    """
    Parse a Go (Gin) main.go router → endpoint records.

    --- CUSTOMIZE ---
    Set GO_MAIN_PATH env var or edit the default above to point to your router file.
    This parser handles standard Gin group/route patterns.
    """
    main_go = repo / GO_MAIN_PATH
    if not main_go.exists():
        print(f"  ⚠ main.go not found at {main_go} — skipping endpoint indexing")
        return []

    text = main_go.read_text(encoding="utf-8")
    records = []

    group_pattern = re.compile(r'\b(\w+)\s*:?=\s*(\w+)\.Group\("([^"]+)"\)')
    group_prefix: dict[str, str] = {"r": ""}

    for _ in range(5):
        for gm in group_pattern.finditer(text):
            var, parent, seg = gm.groups()
            if parent in group_prefix and var not in group_prefix:
                group_prefix[var] = group_prefix[parent] + seg

    route_start = re.compile(
        r'\b(\w+)\s*\.\s*(GET|POST|PUT|PATCH|DELETE)\s*\(\s*"([^"]*)"'
    )
    handler_re = re.compile(r'(\w+)\.(\w+)\s*$')

    for sm in route_start.finditer(text):
        grp, method, path = sm.groups()
        if grp not in group_prefix:
            continue

        depth, i = 1, sm.end()
        while i < len(text) and depth > 0:
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
            i += 1
        args = text[sm.end():i - 1]

        hm = handler_re.search(args.strip())
        handler_fn = f"{hm.group(1)}.{hm.group(2)}" if hm else ""

        line_no = text[:sm.start()].count("\n") + 1
        records.append({
            "method":     method,
            "path":       group_prefix[grp] + path,
            "file":       GO_MAIN_PATH,
            "line":       line_no,
            "handler_fn": handler_fn,
            "spec":       "",
        })

    print(f"  ✓ Indexed {len(records)} API endpoints")
    return records


def index_react_components(repo: Path) -> list[dict]:
    """
    Parse frontend/src/**/*.tsx → component records.

    --- CUSTOMIZE ---
    Change the `src` path if your frontend lives elsewhere.
    """
    records = []
    src = repo / "frontend" / "src"
    if not src.exists():
        print(f"  ⚠ frontend/src not found — skipping component indexing")
        return records

    for tsx in sorted(src.glob("**/*.tsx")):
        rel = str(tsx.relative_to(repo / "frontend"))
        text = tsx.read_text(encoding="utf-8")

        name_m = re.search(r'export default function (\w+)', text)
        if not name_m:
            continue
        name = name_m.group(1)

        hooks = re.findall(r'import\s+{([^}]+)}\s+from\s+[\'"]\.\.?\/hooks\/(\w+)', text)
        hook_names = []
        for names, _ in hooks:
            hook_names.extend(n.strip() for n in names.split(",") if n.strip())

        api_fns = re.findall(r'import\s+{([^}]+)}\s+from\s+[\'"]\.\.?\/api\/(\w+)', text)
        api_names = []
        for names, _ in api_fns:
            api_names.extend(n.strip() for n in names.split(",") if n.strip())

        records.append({
            "name":      name,
            "file":      rel,
            "hooks":     hook_names,
            "api_calls": api_names,
        })

    print(f"  ✓ Indexed {len(records)} React components")
    return records


def index_hooks(repo: Path) -> list[dict]:
    """Parse frontend/src/hooks/*.ts → hook records."""
    records = []
    hooks_dir = repo / "frontend" / "src" / "hooks"
    if not hooks_dir.exists():
        return records

    for f in sorted(hooks_dir.glob("*.ts")):
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r'export function (use\w+)', text):
            records.append({
                "name": m.group(1),
                "file": str(f.relative_to(repo / "frontend")),
            })

    print(f"  ✓ Indexed {len(records)} hooks")
    return records


def index_secondary_context(repo: Path) -> tuple[list[dict], list[dict]]:
    """
    Parse a secondary context file (GEMINI.md / ops-agent context) →
    architectural decisions + additional context records.

    --- CUSTOMIZE ---
    Edit section headings to match your file.
    The "Decisions Already Made" section is parsed generically.
    """
    ctx_path = repo / SECONDARY_CONTEXT_FILE
    if not ctx_path.exists():
        print(f"  ⚠ {SECONDARY_CONTEXT_FILE} not found — skipping")
        return [], []

    text = ctx_path.read_text(encoding="utf-8")
    decisions = []
    context   = []

    def extract_section(heading: str) -> str:
        m = re.search(rf'^## {re.escape(heading)}(.+?)(?=^## |\Z)', text, re.MULTILINE | re.DOTALL)
        return m.group(1).strip() if m else ""

    # Generic: parse "## Decisions Already Made" section
    # Format: - **Topic**: Decision text — Rationale
    decisions_text = extract_section("Decisions Already Made")
    for m in re.finditer(r'^- \*\*([^*]+)\*\*:\s*(.+)', decisions_text, re.MULTILINE):
        topic, rest = m.group(1).strip(), m.group(2).strip()
        if " — " in rest:
            decision, rationale = rest.split(" — ", 1)
        else:
            decision, rationale = rest, ""
        rationale = re.sub(r'\s*\[[A-Z0-9,\.\- ]+\]\s*$', '', rationale).strip()
        decisions.append({
            "topic":     topic,
            "decision":  decision.strip(),
            "rationale": rationale,
            "agent":     "secondary_context",
        })

    # --- CUSTOMIZE: add more section parsers here ---
    # Example: parse an "Infrastructure Stack" section
    #
    # infra_text = extract_section("Infrastructure Stack")
    # if infra_text:
    #     context.append({
    #         "section": "infra",
    #         "key":     "stack",
    #         "content": infra_text.strip(),
    #     })

    print(f"  ✓ Indexed {len(decisions)} decisions + {len(context)} context records from {SECONDARY_CONTEXT_FILE}")
    return decisions, context


def index_services_and_history(repo: Path) -> tuple[list[dict], list[dict]]:
    """
    Parse specs/INDEX.md → service records + history records.

    --- CUSTOMIZE ---
    Edit the section heading strings to match your INDEX.md headings.
    """
    index_md = repo / "specs" / "INDEX.md"
    if not index_md.exists():
        print(f"  ⚠ specs/INDEX.md not found — skipping services/history")
        return [], []

    text = index_md.read_text(encoding="utf-8")
    services = []
    history  = []

    # --- CUSTOMIZE: heading for the services table ---
    SERVICES_HEADING = "## Services"   # change to match your INDEX.md

    # --- CUSTOMIZE: heading for the history table ---
    HISTORY_HEADING = "## Implementation History"  # change to match your INDEX.md

    # Parse services table: | name | `directory/` | ... | status |
    in_services = False
    for line in text.splitlines():
        if SERVICES_HEADING in line:
            in_services = True
            continue
        if in_services:
            if line.startswith("## "):
                break
            m = re.match(r'\|\s*([\w-]+)\s*\|\s*`([^`]+)`\s*\|[^|]+\|\s*(.+?)\s*\|', line)
            if m and m.group(1) not in ("Service", "---", ""):
                name, directory, status = m.group(1), m.group(2), m.group(3)
                services.append({
                    "name":      name.strip(),
                    "directory": directory.strip(),
                    "status":    re.sub(r'[✅🔲]', '', status).strip(),
                })

    # Parse history table: | N | [TICKET-01](...) ✅ | Description |
    in_history = False
    for line in text.splitlines():
        if HISTORY_HEADING in line:
            in_history = True
            continue
        if in_history:
            if line.startswith("## "):
                break
            m = re.match(r'\|\s*(\d+)\s*\|\s*\[([^\]]+)\]\([^)]+\)\s*[✅🔲]?\s*\|\s*(.+?)\s*\|', line)
            if m:
                order, ticket, description = int(m.group(1)), m.group(2).strip(), m.group(3).strip()
                if not history or history[-1]["order"] != order:
                    history.append({
                        "order":       order,
                        "ticket":      ticket,
                        "description": description,
                    })

    print(f"  ✓ Indexed {len(services)} services + {len(history)} history entries from INDEX.md")
    return services, history


# ── SurrealDB writer ──────────────────────────────────────────────────────────

async def write_all(specs, endpoints, components, hooks, context,
                    services, history, secondary_decisions, secondary_context):
    from surrealdb import AsyncSurreal

    async with AsyncSurreal(DB_URL) as db:
        await db.signin({"user": DB_USER, "pass": DB_PASS})
        await db.use(DB_NS, DB_DB)

        print(f"📦 Writing {len(context)} context records...")
        for c in context:
            await db.query(
                "DELETE context WHERE section = $s AND key = $k; CREATE context CONTENT $data",
                {"s": c["section"], "k": c["key"], "data": c}
            )

        print(f"📦 Writing {len(specs)} specs...")
        for s in specs:
            await db.query(
                "DELETE spec WHERE ticket = $t; CREATE spec CONTENT $data",
                {"t": s["ticket"], "data": s}
            )

        print(f"📦 Writing {len(endpoints)} endpoints...")
        for e in endpoints:
            await db.query(
                "DELETE endpoint WHERE path = $p AND method = $m; CREATE endpoint CONTENT $data",
                {"p": e["path"], "m": e["method"], "data": e}
            )

        print(f"📦 Writing {len(components)} components...")
        for c in components:
            await db.query(
                "DELETE component WHERE name = $n; CREATE component CONTENT $data",
                {"n": c["name"], "data": c}
            )

        print(f"📦 Writing {len(hooks)} hooks...")
        for h in hooks:
            await db.query(
                "DELETE hook WHERE name = $n; CREATE hook CONTENT $data",
                {"n": h["name"], "data": h}
            )

        # --- CUSTOMIZE: seed project-specific facts into memory ---
        # known_facts = {
        #     "db_host":  "postgres:5432",
        #     "api_port": "3000",
        # }
        # for k, v in known_facts.items():
        #     await db.query(
        #         "DELETE memory WHERE key = $k; CREATE memory SET key=$k, value=$v, agent='indexer'",
        #         {"k": k, "v": v}
        #     )

        print(f"📦 Writing {len(services)} services...")
        for s in services:
            await db.query(
                "DELETE service WHERE name = $n; CREATE service CONTENT $data",
                {"n": s["name"], "data": s}
            )

        print(f"📦 Writing {len(history)} history entries...")
        for h in history:
            await db.query(
                "DELETE history WHERE ticket = $t; CREATE history CONTENT $data",
                {"t": h["ticket"], "data": h}
            )

        print(f"📦 Writing {len(secondary_decisions)} decisions from {SECONDARY_CONTEXT_FILE}...")
        await db.query("DELETE decision WHERE agent = 'secondary_context'")
        for d in secondary_decisions:
            await db.query("CREATE decision CONTENT $data", {"data": d})

        print(f"📦 Writing {len(secondary_context)} context records from {SECONDARY_CONTEXT_FILE}...")
        for c in secondary_context:
            await db.query(
                "DELETE context WHERE section = $s AND key = $k; CREATE context CONTENT $data",
                {"s": c["section"], "k": c["key"], "data": c}
            )

    print("\n✅ Indexing complete!")


async def main():
    print(f"🔍 Indexing repo at: {REPO}")
    print(f"🗄️  Target: {DB_URL} / {DB_NS}.{DB_DB}\n")

    context                            = index_context_file(REPO)
    specs                              = index_specs(REPO)
    endpoints                          = index_go_routes(REPO)
    components                         = index_react_components(REPO)
    hooks                              = index_hooks(REPO)
    services, history                  = index_services_and_history(REPO)
    secondary_decisions, secondary_ctx = index_secondary_context(REPO)

    await write_all(specs, endpoints, components, hooks, context,
                    services, history, secondary_decisions, secondary_ctx)


if __name__ == "__main__":
    asyncio.run(main())
