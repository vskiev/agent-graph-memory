# brain-task

Load all context needed to work on a specific ticket. Replaces manually reading spec files,
grepping for handlers, and searching components.

Ticket: `$ARGUMENTS`

## Steps

1. Call `get_spec("$ARGUMENTS")` — load spec: status, AC, branch, key files
2. Call `get_decisions("$ARGUMENTS")` — load any past architectural decisions for this ticket
3. Based on the spec's key files and description, call relevant navigation tools:
   - `list_endpoints("/api/...")` — if the spec involves API endpoints
   - `find_handler("/api/...")` — for specific route handlers
   - `find_component("ComponentName")` — for frontend components
   - `what_uses("hookName")` — if a hook is involved
4. Call `claim_task("$ARGUMENTS", "claude", "working on $ARGUMENTS")` — register that you're working on it

Then output a compact task brief:
- Spec status and acceptance criteria
- Key files to touch
- Relevant handlers/components found
- Any past decisions to keep in mind
- Confirm task is claimed

If the spec is not found, stop and report it — do not start coding without a spec.
