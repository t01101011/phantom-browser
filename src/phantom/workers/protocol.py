"""Worker event protocol — structured JSON events with sequence IDs.

Every worker process communicates with the control plane by emitting
JSON event objects to stdout (one per line).  The control plane reads
the event stream and responds accordingly.

Event schema
------------
.. code-block:: json

    {"seq": 1, "type": "start", "data": {"pid": 1234}, "error": null}
    {"seq": 2, "type": "ready",  "data": {"status": "ok"},  "error": null}
    {"seq": 3, "type": "error",  "data": {}, "error": {"code": "NAV_FAIL", "message": "..."}}

- **seq**: monotonic integer, starts at 1, incremented per event.
- **type**: one of ``start``, ``ready``, ``navigate``, ``snapshot``,
  ``screenshot``, ``cookies``, ``storage_state``, ``stopped``, ``error``.
- **data**: action-specific payload dict.
- **error**: optional dict with ``code`` and ``message``; null on success.
"""
from __future__ import annotations

import json
import threading
from typing import Any


class Event:
    """A single structured event from a worker process.

    Parameters
    ----------
    type : str
        Event type (``start``, ``ready``, ``stopped``, ``error``, etc.).
    data : dict
        Event payload.
    error : dict | None
        Error details (``{"code": ..., "message": ...}``) or None.
    """

    _seq_lock = threading.Lock()
    _global_seq = 0

    def __init__(
        self,
        type: str,
        data: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        with self._seq_lock:
            Event._global_seq += 1
            self.seq = Event._global_seq
        self.type = type
        self.data = data or {}
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "seq": self.seq,
            "type": self.type,
            "data": self.data,
            "error": self.error,
        }

    def to_json(self) -> str:
        """Serialize to a JSON string (one line)."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_json(cls, raw: str) -> Event:
        """Deserialize from a JSON string.

        Raises ``ValueError`` if the input is malformed or missing
        required fields.
        """
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed event JSON: {exc}") from exc

        if not isinstance(obj, dict):
            raise ValueError(f"expected dict, got {type(obj).__name__}")
        if "type" not in obj or not obj["type"]:
            raise ValueError("event missing required field: 'type'")

        # Manually set seq for deserialized events (don't increment counter)
        ev = cls.__new__(cls)
        ev.seq = obj.get("seq", 0)
        ev.type = obj["type"]
        ev.data = obj.get("data", {})
        ev.error = obj.get("error")
        return ev

    def __repr__(self) -> str:
        err = f", error={self.error}" if self.error else ""
        return f"<Event #{self.seq} {self.type}{err}>"


def validate_event_sequence(events: list[dict[str, Any]]) -> None:
    """Validate that a list of events has monotonically increasing seq.

    Raises ``ValueError`` if sequence numbers are out of order, have
    gaps, or if any event is missing required fields.
    """
    last_seq = -1
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            raise ValueError(f"event {i}: expected dict, got {type(ev).__name__}")
        if "type" not in ev or not ev["type"]:
            raise ValueError(f"event {i}: missing 'type'")
        seq = ev.get("seq", 0)
        if seq <= last_seq:
            raise ValueError(
                f"event {i}: sequence gap — seq {seq} after {last_seq}"
            )
        last_seq = seq
