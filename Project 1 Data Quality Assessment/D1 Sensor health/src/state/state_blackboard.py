"""state_blackboard.py — JSON-backed state blackboard (v1.1).

Persists state-machine transitions, PELT change-points, and recovery events
for both streaming-batch sync and audit purposes.
"""
from __future__ import annotations
import json, threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class StateEntry:
    sensor_id: str
    flag_name: str
    flag_value: Any
    start_time: str
    expire_at: Optional[str] = None
    source: str = "streaming"
    run_id: str = ""
    metadata: Dict = field(default_factory=dict)


class StateBlackboard:
    def __init__(self, path: Path, batch_mode: bool = True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._batch_mode = batch_mode
        self._buffer: List[Dict] = []
        if not self.path.exists():
            self._save([])

    def _save(self, entries):
        with open(self.path, "w") as f:
            json.dump(entries, f, indent=2, default=str)

    def _load(self):
        if not self.path.exists(): return []
        with open(self.path) as f: return json.load(f)

    def write(self, entry: StateEntry):
        if self._batch_mode:
            self._buffer.append(asdict(entry)); return
        with self._lock:
            entries = self._load(); entries.append(asdict(entry)); self._save(entries)

    def write_many(self, entries):
        if self._batch_mode:
            for e in entries:
                self._buffer.append(asdict(e) if hasattr(e, '__dataclass_fields__') else dict(e))
            return
        with self._lock:
            existing = self._load()
            existing.extend([asdict(e) if hasattr(e, '__dataclass_fields__') else dict(e)
                              for e in entries])
            self._save(existing)

    def flush(self):
        if not self._buffer: return
        with self._lock:
            existing = self._load()
            existing.extend(self._buffer)
            self._save(existing)
            self._buffer = []

    def all_entries(self):
        return self._load() + self._buffer

    def clear(self):
        self._save([])
