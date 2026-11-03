"""Ephemeral single-process request control; never persists questions or chats.

Single-process deployment matches the current app. Multiple workers/replicas
need a shared atomic limiter/idempotency store before enabling chat there.
"""
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from fastapi import HTTPException


@dataclass
class Slot:
    user: str
    digest: str
    created: float
    result: dict | None = None


class ChatRequests:
    def __init__(self):
        self.lock = Lock()
        self.slots = {}
        self.users = defaultdict(deque)

    def reserve(self, user, request_id, digest):
        now = monotonic()
        with self.lock:
            self.slots = {k: v for k, v in self.slots.items() if now-v.created < 600}
            for uid in list(self.users):
                while self.users[uid] and now-self.users[uid][0] >= 3600:
                    self.users[uid].popleft()
                if not self.users[uid]:
                    del self.users[uid]
            slot = self.slots.get((user, str(request_id)))
            if slot and slot.digest != digest:
                raise HTTPException(409, "This question changed. Submit it as a new question.")
            if not slot:
                slot = next((v for v in self.slots.values() if v.user == user and v.digest == digest and now-v.created < 15), None)
            if slot:
                if slot.result is None:
                    raise HTTPException(409, "This question is already being reviewed. Wait for its answer; it was not sent again.")
                return slot, slot.result
            if any(v.user == user and v.result is None for v in self.slots.values()):
                raise HTTPException(409, "Another question is already being reviewed. Wait before asking a follow-up.")
            recent = self.users[user]
            if sum(now-t < 60 for t in recent) >= 6 or len(recent) >= 30 or len(self.slots) >= 4096:
                raise HTTPException(429, "Please pause before asking another question. Basic analysis and replay remain available.", headers={"Retry-After": "60"})
            recent.append(now)
            slot = Slot(user, digest, now)
            self.slots[(user, str(request_id))] = slot
            return slot, None

    def finish(self, slot, result):
        with self.lock:
            slot.result = result


chat_requests = ChatRequests()
