#!/usr/bin/env python3
"""
Agent Graph Memory — File Watcher
Watches /repo for changes to .go, .tsx, .ts, .md files
and auto-reindexes the knowledge graph with 10s debounce.
"""
import os
import time
import threading
import subprocess
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watcher] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

REPO     = Path(os.getenv("REPO_PATH", "/repo"))
DEBOUNCE = float(os.getenv("WATCHER_DEBOUNCE", "10"))

WATCH_EXTENSIONS = {".go", ".tsx", ".ts", ".md"}
SKIP_DIRS        = {"node_modules", ".git", "dist", "__pycache__", "vendor", "data"}


class ReindexHandler(FileSystemEventHandler):
    def __init__(self):
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._running = False

    def on_any_event(self, event):
        if event.is_directory:
            return

        path = Path(event.src_path)

        if path.suffix not in WATCH_EXTENSIONS:
            return
        if any(skip in path.parts for skip in SKIP_DIRS):
            return

        log.info(f"Changed: {path.relative_to(REPO) if REPO in path.parents else path.name}")
        self._schedule_reindex()

    def _schedule_reindex(self):
        with self._lock:
            if self._running:
                return
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE, self._reindex)
            self._timer.daemon = True
            self._timer.start()

    def _reindex(self):
        with self._lock:
            self._running = True
        try:
            log.info("Reindexing knowledge graph...")
            result = subprocess.run(
                ["python3", "/app/indexer.py"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if any(c in line for c in ["✓", "✅", "⚠"]):
                        log.info(line.strip())
            else:
                log.error(f"Indexer failed:\n{result.stderr[:500]}")
        except subprocess.TimeoutExpired:
            log.error("Indexer timed out after 120s")
        except Exception as e:
            log.error(f"Indexer error: {e}")
        finally:
            with self._lock:
                self._running = False


def main():
    if not REPO.exists():
        log.error(f"Repo path not found: {REPO}")
        return

    handler = ReindexHandler()
    observer = Observer()
    observer.schedule(handler, str(REPO), recursive=True)
    observer.start()

    log.info(f"Watching {REPO} (debounce {DEBOUNCE}s, extensions: {', '.join(sorted(WATCH_EXTENSIONS))})")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
