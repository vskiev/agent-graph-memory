# brain-done

Close out a completed task and hand off to the other agent if needed.

Ticket: `$ARGUMENTS`

## Steps

1. Call `update_spec_status("$ARGUMENTS", "done", "claude")` — mark spec as done
2. Call `release_task("$ARGUMENTS", "claude")` — release the claim
3. Call `end_session("claude", "...")` — save session summary:
   - What was implemented
   - What was NOT done (if anything from AC was skipped)
   - Any blockers or known issues
4. Ask the user: "Does the other agent need to know about this?" — if yes, call:
   `leave_note("gemini", "$ARGUMENTS", "message describing what was done and what they should do next", "claude")`

Then output:
- Confirmation that task is closed
- Session summary saved
- Whether a note was left for the other agent

If `$ARGUMENTS` is empty, ask which ticket to close.
