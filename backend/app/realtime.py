import asyncio
from collections import defaultdict

from fastapi import WebSocket


class RealtimeHub:
    def __init__(self):
        self.connections: dict[str, dict[WebSocket, str]] = defaultdict(dict)

    def online_ids(self, topic_id: str) -> set[str]:
        return set(self.connections[topic_id].values())

    async def connect(self, topic_id: str, user_id: str, socket: WebSocket):
        await socket.accept()
        self.connections[topic_id][socket] = user_id
        await self.broadcast(topic_id, {"type": "presence"})

    async def disconnect(self, topic_id: str, socket: WebSocket):
        self.connections[topic_id].pop(socket, None)
        await self.broadcast(topic_id, {"type": "presence"})

    async def broadcast(self, topic_id: str, event: dict):
        # Events carry only an invalidation hint, never group messages, metrics or secrets.
        sockets = list(self.connections[topic_id])
        if not sockets:
            return
        results = await asyncio.gather(
            *(socket.send_json(event) for socket in sockets), return_exceptions=True
        )
        for socket, result in zip(sockets, results):
            if isinstance(result, Exception):
                self.connections[topic_id].pop(socket, None)

    async def revoke_user(self, user_id: str):
        for connections in self.connections.values():
            for socket, connected_user in list(connections.items()):
                if connected_user == user_id:
                    connections.pop(socket, None)
                    await socket.close(code=4401)

    async def revoke_topic_member(self, topic_id: str, user_id: str):
        connections = self.connections[topic_id]
        for socket, connected_user in list(connections.items()):
            if connected_user == user_id:
                connections.pop(socket, None)
                await socket.close(code=4403)


hub = RealtimeHub()
