"""
In-memory pub/sub for SSE streaming of estimate workflow events.
Single-process only — safe because asyncio is single-threaded.
"""
import asyncio
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_subscribers: Dict[str, List[asyncio.Queue]] = {}
_active: set = set()


def start(estimate_id: str) -> None:
    _active.add(estimate_id)


def stop(estimate_id: str) -> None:
    """Mark estimate as done and notify all subscribers."""
    _active.discard(estimate_id)
    publish(estimate_id, {"type": "done"})


def subscribe(estimate_id: str) -> Optional[asyncio.Queue]:
    """
    Subscribe to events for estimate_id.
    Returns None if the estimate is not currently active (already done).
    """
    if estimate_id not in _active:
        return None
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.setdefault(estimate_id, []).append(q)
    return q


def unsubscribe(estimate_id: str, queue: asyncio.Queue) -> None:
    subs = _subscribers.get(estimate_id, [])
    if queue in subs:
        subs.remove(queue)
    if not subs:
        _subscribers.pop(estimate_id, None)


def publish(estimate_id: str, event: dict) -> None:
    for q in _subscribers.get(estimate_id, []):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"SSE queue full for {estimate_id}, dropping event")
