# brain-pr

Create a GitHub PR for a completed ticket. Auto-fills AC checklist and summary from the graph.

Ticket: `$ARGUMENTS`

## Steps

1. **In parallel**, gather all context:
   - `get_spec("$ARGUMENTS")` — spec with AC list, branch name, key files
   - Run: `git log main..HEAD --oneline`
   - Run: `git diff main..HEAD --name-only`

2. Build the PR body using spec data:
   - Title: one-line description from spec (under 70 chars)
   - AC checklist: each acceptance criterion from spec as `- [x] AC-N: <text> — DONE`
     Mark as `- [ ] NOT DONE` only if explicitly skipped/noted in conversation
   - Files changed: from git diff output, annotated with why each was touched
   - Not covered: anything from spec that was intentionally left out

3. Run: `gh pr create --title "<title>" --body "$(cat <<'EOF' ... EOF)"`

   Use this PR body format:
   ```
   ## Spec
   <service>/specs/<TICKET>-<description>.md

   ## Acceptance Criteria
   - [x] AC-1: <description> — DONE
   - [x] AC-2: <description> — DONE

   ## Files changed
   - `path/to/file.go` — <why>
   - `path/to/component.tsx` — <why>

   ## Not covered
   <anything from spec not implemented, or "All AC covered">

   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   ```

4. Call `update_spec_status("$ARGUMENTS", "done", "claude")`
5. Call `release_task("$ARGUMENTS", "claude")`

Output: PR URL + confirmation that spec is marked done.

If `$ARGUMENTS` is empty, ask which ticket to create a PR for.
If no spec found, stop — do not create a PR without a spec.
