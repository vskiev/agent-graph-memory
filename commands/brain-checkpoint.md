# brain-checkpoint

Save current progress to the graph. Call this after completing a meaningful step
(e.g. after writing a handler, finishing a component, fixing a bug).

## Steps

1. Look at what files you've touched in this conversation
2. Call `update_session("claude", ["list", "of", "touched", "files"], "$ARGUMENTS")` — log progress
3. If a spec status changed (e.g. started → in-progress, or finished → done):
   - Call `update_spec_status("TICKET", "new-status", "claude")`
4. If you made an architectural decision during this work:
   - Call `log_decision("topic", "decision", "reason", "claude")`

Then confirm: "Checkpoint saved — [brief summary of what was logged]"

If `$ARGUMENTS` is empty, summarize what was done based on conversation context.
