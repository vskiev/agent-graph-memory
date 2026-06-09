# brain-init

Load full context from the graph memory database at the start of a conversation.
Run this instead of reading CLAUDE.md or project files manually.

## Steps

1. Call `start_session("claude", "$ARGUMENTS")` — registers this session and returns where you left off last time

2. **In parallel**, call all of these at once:
   - `get_last_session("")` — what both Claude and Gemini did recently
   - `read_notes("claude")` — unread messages from Gemini
   - `active_tasks()` — currently claimed tickets
   - `get_project_context("module")` — modules overview instead of reading CLAUDE.md

Then output a compact briefing (5–10 lines max):
- What was done last session
- Any unread notes from Gemini
- Active tasks and who owns them
- Modules status

If `$ARGUMENTS` is empty, use "starting session" as the task description.
