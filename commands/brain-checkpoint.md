# brain-checkpoint

Save current progress to the graph. Call after completing a meaningful step.

## Steps

1. Look at what files you've touched in this conversation
2. Call `update_session("claude", ["list", "of", "touched", "files"], "$ARGUMENTS")`
3. If a spec status changed → call `update_spec_status("TICKET", "new-status", "claude")`

4. **Auto-detect architectural decisions** — scan the recent conversation for patterns:
   - Phrases like "because", "instead of", "we decided", "виріш", "замість", "тому що"
   - Any choice between two options ("X not Y", "X замість Y")
   - Any constraint or tradeoff mentioned
   
   For each decision found, call:
   `log_decision("topic", "decision made", "reason/rationale", "claude")`
   
   Examples of what to detect:
   - "Використовуємо батч INSERT замість per-message" → log_decision("storage", "batch INSERT", "performance")
   - "Пінимо SurrealDB v2.6.5 бо v3 дропає параметри" → log_decision("surrealdb", "pin v2.6.5", "v3 drops query params")
   - "JWT не сесії бо stateless для k8s" → log_decision("auth", "JWT not sessions", "stateless for k8s")

5. Confirm: "Checkpoint saved — files: X, decisions logged: Y"

If `$ARGUMENTS` is empty, summarize based on conversation context.
