# brain-init

Load full context from the graph memory database at the start of a conversation.
Run this instead of reading your context file or project files manually.

Copy to `~/.claude/commands/brain-init.md` for global access,
or to `.claude/commands/brain-init.md` in your project root.

## Steps

1. Call `start_session("claude", "$ARGUMENTS")` — registers this session and returns where you left off last time
2. Call `get_last_session("")` — shows what both Claude and Gemini did recently
3. Call `read_notes("claude")` — read any unread messages from Gemini
4. Call `active_tasks()` — check what tickets are currently claimed
5. Call `get_project_context("module")` — load the modules overview instead of reading your context file

Then output a compact briefing (5–10 lines max):
- What was done last session
- Any unread notes from Gemini
- Active tasks and who owns them
- What modules/context was loaded

If `$ARGUMENTS` is empty, use "starting session" as the task description.
