# brain-reindex

Reindex the codebase into the graph memory database. Run after merging a PR or
when the graph feels out of sync with the actual code.

## Steps

1. Run the shell command (replace `<mcp_container>` with your container name):
   ```
   docker exec <mcp_container> python3 /app/indexer.py
   ```
2. If `$ARGUMENTS` is "sync" or "full", also run spec sync:
   ```
   docker exec <mcp_container> python3 /app/sync_specs.py
   ```
3. Report what was indexed (the indexer prints a summary)

## When to run

- After `git merge` or `git pull` on main
- After adding new API endpoints or components
- After updating spec statuses in PROJ files
- When `find_handler()` or `find_component()` returns stale or missing results

## Automate with a post-merge hook

```bash
# .git/hooks/post-merge
#!/bin/bash
docker exec <mcp_container> python3 /app/indexer.py 2>/dev/null &
echo "Graph memory: reindexing in background..."
```
