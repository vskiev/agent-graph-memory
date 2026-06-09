#!/usr/bin/env python3
"""
CivicChain Graph Indexer
Parses the repo and populates SurrealDB with the knowledge graph.

Run after merges:
  docker exec civicchain_mcp python3 /app/indexer.py

Or locally (needs surrealdb pip package):
  SURREALDB_URL=ws://localhost:8000/rpc python3 indexer.py
"""
import asyncio
import os
import re
import json
from pathlib import Path

REPO        = Path(os.getenv("REPO_PATH", "/repo"))
DB_URL      = os.getenv("SURREALDB_URL",  "ws://surrealdb:8000/rpc")
DB_USER     = os.getenv("SURREALDB_USER", "root")
DB_PASS     = os.getenv("SURREALDB_PASS", "root_password")
DB_NS       = os.getenv("SURREALDB_NS",   "civicchain")
DB_DB       = os.getenv("SURREALDB_DB",   "main")


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
    """Extract acceptance criteria from spec markdown.
    Supports both '- [ ] **AC-1**: text' and plain '- [ ] text' formats.
    Only parses lines within the Acceptance Criteria section.
    """
    items = []
    in_section = False
    idx = 1
    for line in text.splitlines():
        if re.search(r'acceptance criteria|## AC', line, re.IGNORECASE):
            in_section = True
            continue
        if in_section:
            if line.startswith('#'):
                break
            m = re.match(r'\s*- \[([ xX])\] \*\*?(AC-\d+)\*\*?:?\s*(.+)', line)
            if m:
                items.append({"id": m.group(2), "done": m.group(1).lower() == "x", "text": m.group(3).strip()})
                idx += 1
            else:
                m2 = re.match(r'\s*- \[([ xX])\] (.+)', line)
                if m2:
                    items.append({"id": f"AC-{idx}", "done": m2.group(1).lower() == "x", "text": m2.group(2).strip()})
                    idx += 1
    return items


def parse_key_files(text: str) -> list[str]:
    """Extract key files list from spec markdown."""
    files = []
    in_section = False
    for line in text.splitlines():
        if "ключові файли" in line.lower() or "ключевые файлы" in line.lower():
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

def index_claude_md(repo: Path) -> list[dict]:
    """Parse CLAUDE.md → context records by section."""
    claude_md = repo / "CLAUDE.md"
    if not claude_md.exists():
        print(f"  ⚠ CLAUDE.md not found")
        return []

    text = claude_md.read_text(encoding="utf-8")
    records = []

    def extract_section(heading: str) -> str:
        """Extract text from ## heading until next ##."""
        m = re.search(rf'^## {re.escape(heading)}(.+?)(?=^## |\Z)', text, re.MULTILINE | re.DOTALL)
        return m.group(1).strip() if m else ""

    # Mission
    mission = extract_section("Миссия проекта")
    if mission:
        records.append({"section": "mission", "key": "mission", "content": mission})

    # Architecture (summary without code blocks)
    arch = extract_section("Архитектура")
    if arch:
        records.append({"section": "architecture", "key": "overview", "content": arch})

    # Modules — parse table rows with status ✅/post-MVP/draft
    modules_text = extract_section("Модули платформы")
    for m in re.finditer(r'\*\*(\w+)\*\*\s*([✅🔲]?)\s*—\s*([^\n;]+)', modules_text):
        name, status_icon, desc = m.groups()
        status = "mvp" if "✅" in status_icon else "post-mvp"
        records.append({
            "section": "module",
            "key":     name,
            "content": desc.strip(),
            "status":  status,
        })

    # Contracts — parse from смарт-контракты section
    contracts_text = extract_section("Смарт-контракты")
    for m in re.finditer(r'Адрес[^`]*`(0x[0-9a-fA-F]+)`', contracts_text):
        addr = m.group(1)
        # find contract name above this address line
        before = contracts_text[:m.start()]
        name_m = re.findall(r'### (\w+\.sol)', before)
        name = name_m[-1] if name_m else "unknown"
        records.append({"section": "contract", "key": name, "content": addr})

    # Constants
    constants_text = extract_section("Важные константы")
    for m in re.finditer(r'(\w+)\s*=\s*(\d+)\s*//\s*(.+)', constants_text):
        records.append({
            "section": "constant",
            "key":     m.group(1),
            "content": m.group(2),
            "comment": m.group(3).strip(),
        })

    # Dev commands (quick start)
    commands_text = extract_section("Команды для быстрого старта")
    if commands_text:
        records.append({"section": "commands", "key": "quickstart", "content": commands_text})

    print(f"  ✓ Indexed {len(records)} context records from CLAUDE.md")
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
    """Parse main.go router setup → endpoint records with full paths."""
    main_go = repo / "civicchain" / "api" / "cmd" / "server" / "main.go"
    if not main_go.exists():
        print(f"  ⚠ main.go not found at {main_go}")
        return []

    text = main_go.read_text(encoding="utf-8")
    records = []

    # Step 1: build group prefix map from Group() declarations.
    # Matches: varname := parent.Group("/prefix") or varname = parent.Group("/prefix")
    group_pattern = re.compile(
        r'\b(\w+)\s*:?=\s*(\w+)\.Group\("([^"]+)"\)'
    )
    # Seed with the root router (r has no prefix)
    group_prefix: dict[str, str] = {"r": ""}

    # Iterate until no more resolutions (handles chains like ap = cp.Group(...))
    for _ in range(5):
        for gm in group_pattern.finditer(text):
            var, parent, seg = gm.groups()
            if parent in group_prefix and var not in group_prefix:
                group_prefix[var] = group_prefix[parent] + seg

    # Step 2: extract route declarations, handling nested parens for middleware args
    route_start = re.compile(
        r'\b(\w+)\s*\.\s*(GET|POST|PUT|PATCH|DELETE)\s*\(\s*"([^"]*)"'
    )
    # Last word.word before closing paren — the actual handler
    handler_re = re.compile(r'(\w+)\.(\w+)\s*$')

    for sm in route_start.finditer(text):
        grp, method, path = sm.groups()
        if grp not in group_prefix:
            continue

        # Walk forward from match end to find the matching closing paren
        depth, i = 1, sm.end()
        while i < len(text) and depth > 0:
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
            i += 1
        args = text[sm.end():i - 1]  # everything inside the route call

        # Handler is the last word.word token
        hm = handler_re.search(args.strip())
        handler_fn = f"{hm.group(1)}.{hm.group(2)}" if hm else ""

        line_no = text[:sm.start()].count("\n") + 1
        records.append({
            "method":     method,
            "path":       group_prefix[grp] + path,
            "file":       "civicchain/api/cmd/server/main.go",
            "line":       line_no,
            "handler_fn": handler_fn,
            "spec":       "",
        })

    print(f"  ✓ Indexed {len(records)} API endpoints")
    return records


def index_react_components(repo: Path) -> list[dict]:
    """Parse frontend/src/pages + components/*.tsx → component records."""
    records = []
    src = repo / "frontend" / "src"
    if not src.exists():
        print(f"  ⚠ frontend/src not found")
        return records

    for tsx in sorted(src.glob("**/*.tsx")):
        rel = str(tsx.relative_to(repo / "frontend"))
        text = tsx.read_text(encoding="utf-8")

        # Component name from export default function X
        name_m = re.search(r'export default function (\w+)', text)
        if not name_m:
            continue
        name = name_m.group(1)

        # Hooks used (from hooks/ directory)
        hooks = re.findall(r'import\s+{([^}]+)}\s+from\s+[\'"]\.\.?\/hooks\/(\w+)', text)
        hook_names = []
        for names, _ in hooks:
            hook_names.extend(n.strip() for n in names.split(",") if n.strip())

        # API functions used
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


def index_ts_types(repo: Path) -> list[dict]:
    """Parse frontend/src/**/*.ts → TypeScript interface/type/enum records."""
    records = []
    src = repo / "frontend" / "src"
    if not src.exists():
        print("  ⚠ frontend/src not found — skipping TS type indexing")
        return records

    for ts_file in sorted(src.glob("**/*.ts")):
        rel = str(ts_file.relative_to(repo / "frontend"))
        try:
            text = ts_file.read_text(encoding="utf-8")
        except Exception:
            continue

        for m in re.finditer(r'export\s+interface\s+(\w+)[^{]*\{([^}]*)\}', text, re.DOTALL):
            name, body = m.group(1), m.group(2)
            fields = []
            for line in body.splitlines():
                line = line.strip()
                if ':' in line and not line.startswith('//') and not line.startswith('*'):
                    field = line.split(':')[0].strip().rstrip('?')
                    if field and re.match(r'^\w+$', field):
                        fields.append(field)
            records.append({"name": name, "kind": "interface", "file": rel, "fields": fields[:15]})

        for m in re.finditer(r'export\s+type\s+(\w+)\s*=\s*([^\n;]{1,200})', text):
            name = m.group(1)
            definition = m.group(2).strip().rstrip(';')
            records.append({"name": name, "kind": "type", "file": rel, "fields": [definition[:100]]})

        for m in re.finditer(r'export\s+enum\s+(\w+)\s*\{([^}]*)\}', text, re.DOTALL):
            name, body = m.group(1), m.group(2)
            values = []
            for line in body.splitlines():
                line = line.strip().split('=')[0].strip().rstrip(',')
                if line and not line.startswith('//') and re.match(r'^\w+$', line):
                    values.append(line)
            records.append({"name": name, "kind": "enum", "file": rel, "fields": values[:15]})

    print(f"  ✓ Indexed {len(records)} TypeScript types")
    return records


def index_gemini_md(repo: Path) -> tuple[list[dict], list[dict]]:
    """Parse GEMINI.md → architectural decisions + GCP context records."""
    gemini_md = repo / "GEMINI.md"
    if not gemini_md.exists():
        print(f"  ⚠ GEMINI.md not found")
        return [], []

    text = gemini_md.read_text(encoding="utf-8")
    decisions = []
    context   = []

    def extract_section(heading: str) -> str:
        m = re.search(rf'^## {re.escape(heading)}(.+?)(?=^## |\Z)', text, re.MULTILINE | re.DOTALL)
        return m.group(1).strip() if m else ""

    # ── Decisions Already Made ────────────────────────────────────────
    decisions_text = extract_section("Decisions Already Made")
    for m in re.finditer(r'^- \*\*([^*]+)\*\*:\s*(.+)', decisions_text, re.MULTILINE):
        topic, rest = m.group(1).strip(), m.group(2).strip()
        if " — " in rest:
            decision, rationale = rest.split(" — ", 1)
        else:
            decision, rationale = rest, ""
        # strip trailing [TICKET-REF]
        rationale = re.sub(r'\s*\[[A-Z0-9,\.\- ]+\]\s*$', '', rationale).strip()
        decisions.append({
            "topic":     topic,
            "decision":  decision.strip(),
            "rationale": rationale,
            "agent":     "gemini_md",
        })

    # ── CivicPoll V1→V3 Roadmap table ────────────────────────────────
    roadmap_text = extract_section("CivicPoll Architecture Roadmap")
    if roadmap_text:
        context.append({
            "section": "civicpoll_roadmap",
            "key":     "v1_v3",
            "content": roadmap_text.strip(),
        })

    # ── GCP Production stack ──────────────────────────────────────────
    infra_text = extract_section("Infrastructure Stack")
    gcp_m = re.search(r'### Production: GCP(.+?)###', infra_text, re.DOTALL)
    if gcp_m:
        context.append({
            "section": "gcp_stack",
            "key":     "production",
            "content": gcp_m.group(1).strip(),
        })

    # ── Secret Manager names ──────────────────────────────────────────
    secrets_text = extract_section("Secret Manager Structure")
    if secrets_text:
        context.append({
            "section": "secrets",
            "key":     "gcp_secret_manager",
            "content": secrets_text.strip(),
        })

    print(f"  ✓ Indexed {len(decisions)} decisions + {len(context)} GCP context records from GEMINI.md")
    return decisions, context


def index_index_md(repo: Path) -> tuple[list[dict], list[dict]]:
    """Parse specs/INDEX.md → service records + history records."""
    index_md = repo / "specs" / "INDEX.md"
    if not index_md.exists():
        print(f"  ⚠ specs/INDEX.md not found")
        return [], []

    text = index_md.read_text(encoding="utf-8")
    services = []
    history  = []

    # ── Services table ────────────────────────────────────────────────
    # | blockchain | `civicchain/` | [OVERVIEW.md](...) | ✅ works... |
    in_services = False
    for line in text.splitlines():
        if "## Сервисы" in line:
            in_services = True
            continue
        if in_services:
            if line.startswith("## "):
                break
            m = re.match(r'\|\s*([\w-]+)\s*\|\s*`([^`]+)`\s*\|[^|]+\|\s*(.+?)\s*\|', line)
            if m and m.group(1) not in ("Сервис", "---", ""):
                name, directory, status = m.group(1), m.group(2), m.group(3)
                services.append({
                    "name":      name.strip(),
                    "directory": directory.strip(),
                    "status":    re.sub(r'[✅🔲]', '', status).strip(),
                })

    # ── History table ─────────────────────────────────────────────────
    # | 42 | [CIVICLIVE-01](...) ✅ | CivicLive: /ask /answer... |
    in_history = False
    for line in text.splitlines():
        if "## История реализации" in line:
            in_history = True
            continue
        if in_history:
            if line.startswith("## "):
                break
            m = re.match(r'\|\s*(\d+)\s*\|\s*\[([^\]]+)\]\([^)]+\)\s*[✅🔲]?\s*\|\s*(.+?)\s*\|', line)
            if m:
                order, ticket, description = int(m.group(1)), m.group(2).strip(), m.group(3).strip()
                # skip duplicate rows (same order number)
                if not history or history[-1]["order"] != order:
                    history.append({
                        "order":       order,
                        "ticket":      ticket,
                        "description": description,
                    })

    print(f"  ✓ Indexed {len(services)} services + {len(history)} history entries from INDEX.md")
    return services, history


# ── SurrealDB writer ──────────────────────────────────────────────────────────

async def write_all(specs, endpoints, components, hooks, tstypes, context, services, history, gemini_decisions, gemini_context):
    from surrealdb import AsyncSurreal

    async with AsyncSurreal(DB_URL) as db:
        await db.signin({"username": DB_USER, "password": DB_PASS})
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

        print(f"📦 Writing {len(tstypes)} TypeScript types...")
        for t in tstypes:
            await db.query(
                "DELETE tstype WHERE name = $n AND file = $f; CREATE tstype CONTENT $data",
                {"n": t["name"], "f": t["file"], "data": t}
            )

        known_facts = {
            "mandate_contract":   "0x42699A7612A82f1d9C36148af9C77354759b210b",
            "civicvote_contract": "0x4245CF4518CB2C280f5e9c6a03c90C147F80B4d9",
            "chain_id":           "1337",
            "besu_rpc":           "http://localhost:8545",
            "api_port":           "3000",
            "tender_port":        "3001",
            "ch_port":            "8123",
            "gateway":            "http://localhost (APISIX port 80)",
        }
        for k, v in known_facts.items():
            await db.query(
                "DELETE kv_store WHERE key = $k; CREATE kv_store SET key=$k, val=$v, agent='indexer'",
                {"k": k, "v": v}
            )

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

        # Gemini decisions — delete previous indexer batch, preserve runtime decisions
        print(f"📦 Writing {len(gemini_decisions)} decisions from GEMINI.md...")
        await db.query("DELETE decision WHERE agent = 'gemini_md'")
        for d in gemini_decisions:
            await db.query(
                "CREATE decision CONTENT $data",
                {"data": {**d, "created_at": "2026-06-08T00:00:00Z"}}
            )

        print(f"📦 Writing {len(gemini_context)} GCP context records from GEMINI.md...")
        for c in gemini_context:
            await db.query(
                "DELETE context WHERE section = $s AND key = $k; CREATE context CONTENT $data",
                {"s": c["section"], "k": c["key"], "data": c}
            )

    print("\n✅ Indexing complete!")


async def main():
    print(f"🔍 Indexing CivicChain repo at: {REPO}")
    print(f"🗄️  Target: {DB_URL} / {DB_NS}.{DB_DB}\n")

    context                        = index_claude_md(REPO)
    specs                          = index_specs(REPO)
    endpoints                      = index_go_routes(REPO)
    components                     = index_react_components(REPO)
    hooks                          = index_hooks(REPO)
    tstypes                        = index_ts_types(REPO)
    services, history              = index_index_md(REPO)
    gemini_decisions, gemini_ctx   = index_gemini_md(REPO)

    await write_all(specs, endpoints, components, hooks, tstypes, context, services, history, gemini_decisions, gemini_ctx)


if __name__ == "__main__":
    asyncio.run(main())
