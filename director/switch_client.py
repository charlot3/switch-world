"""Switch transport for the director.

The director is a Console-managed Switch agent (so it is owned by the user and the cast
accepts its messages). Its credentials live in `.switch/agents/director.json`; the room is
discovered by name, so no hard-coded room id is needed.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CREDS = ROOT / "director" / ".switch" / "agents" / "director.json"


class SwitchError(RuntimeError):
    pass


class SwitchClient:
    def __init__(
        self,
        creds_path: Path | str = DEFAULT_CREDS,
        base_url: str | None = None,
        agent_id: str | None = None,
        token: str | None = None,
    ):
        env: dict[str, str] = {}
        path = Path(creds_path)
        if path.exists():
            env = json.loads(path.read_text()).get("env", {})
        self.base_url = (base_url or env.get("SWITCH_API_ENDPOINT") or "http://127.0.0.1:8000").rstrip("/")
        self.agent_id = agent_id or env.get("SWITCH_AGENT_ID")
        self.token = token or env.get("SWITCH_API_TOKEN")
        if not self.agent_id or not self.token:
            raise SwitchError(
                "no director Switch credentials: create the director agent in Console, "
                "or pass --base/--agent/--token"
            )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _op(self, name: str, payload: dict | None = None) -> dict:
        response = httpx.post(
            f"{self.base_url}/agents/{self.agent_id}/ops/{name}",
            headers=self._headers(),
            json=payload or {},
            timeout=20,
        )
        if response.status_code != 200:
            raise SwitchError(f"{name}: {response.status_code} {response.text[:300]}")
        return response.json().get("result", {})

    def find_room(self, name: str = "world") -> dict:
        rooms = self._op("list_rooms")
        # list_rooms returns a list directly; list_all_rooms wraps it in {"result": [...]} in
        # some builds, so accept both.
        if isinstance(rooms, dict):
            rooms = rooms.get("result", [])
        for room in rooms:
            if room.get("name") == name:
                return room
        raise SwitchError(f"room not found: {name}")

    def post(self, room_id: str, content: str) -> dict:
        response = httpx.post(
            f"{self.base_url}/agents/{self.agent_id}/message",
            headers=self._headers(),
            json={"room_id": room_id, "content": content},
            timeout=30,
        )
        if response.status_code != 200:
            raise SwitchError(f"post: {response.status_code} {response.text[:300]}")
        return response.json()

    def history(self, room_id: str) -> list[dict]:
        response = httpx.get(
            f"{self.base_url}/agents/{self.agent_id}/rooms/{room_id}/history",
            headers=self._headers(),
            timeout=30,
        )
        if response.status_code != 200:
            raise SwitchError(f"history: {response.status_code} {response.text[:300]}")
        return response.json().get("events", [])

    def wait_for(
        self,
        room_id: str,
        sender_name: str,
        after_ms: int,
        timeout: float = 90.0,
        poll: float = 1.0,
    ) -> dict | None:
        """Wait for the first event from sender_name newer than after_ms."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            for event in self.history(room_id):
                if (
                    event.get("sender_name") == sender_name
                    and int(event.get("timestamp") or 0) > after_ms
                    and event.get("body")
                ):
                    return event
            time.sleep(poll)
        return None
