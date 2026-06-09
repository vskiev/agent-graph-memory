# brain-task

Load all context needed to work on a specific ticket. Replaces manually reading spec files,
grepping for handlers, and searching components.

Ticket: `$ARGUMENTS`

## Steps

1. Call `get_spec("$ARGUMENTS")` — load spec: status, AC, branch, key files

2. **In parallel**, call all of these at once:
   - `get_decisions("$ARGUMENTS")` — past architectural decisions for this ticket
   - `claim_task("$ARGUMENTS", "claude", "working on $ARGUMENTS")` — register ownership
   - `get_module_context("$ARGUMENTS")` — deep module context (endpoints + components) if module name matches
   - Based on spec's key files, also call as many as apply:
     - `list_endpoints("/api/...")` — if spec involves API endpoints
     - `find_handler("/api/...")` — for a specific route handler
     - `find_component("ComponentName")` — for frontend components
     - `what_uses("hookName")` — if a hook/symbol is involved
     - `get_service("api")` — for service-level context (files, ports, dependencies)

Then output a compact task brief:
- Spec status and acceptance criteria
- Key files to touch
- Relevant handlers/components found
- Any past decisions to keep in mind
- Confirm task is claimed

If the spec is not found, stop and report it — do not start coding without a spec.
