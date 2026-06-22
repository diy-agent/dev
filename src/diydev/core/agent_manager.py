"""
AgentManager — 多 agent 管理器，全 async。

支持后端:
  hermes — AcpAgent  ()
  pi     — PiRpcAgent (provider, model)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from .backend import AgentBackend, AgentCallbacks, AgentState

logger = logging.getLogger("diy.agent_mgr")

BackendKind = Literal["hermes", "pi"]

_default_manager: AgentManager | None = None


def get_manager() -> AgentManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = AgentManager()
    return _default_manager


def reset_manager() -> None:
    global _default_manager
    _default_manager = None


class AgentManager:
    def __init__(self) -> None:
        self._agents: dict[str, AgentBackend] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def get_or_create(
        self,
        task_uri: str,
        cwd: str | None = None,
        *,
        backend: BackendKind = "hermes",
        provider: str | None = None,
        model: str | None = None,
        callbacks: AgentCallbacks | None = None,
    ) -> AgentBackend:
        existing = self._agents.get(task_uri)
        if existing is not None and existing.is_alive:
            return existing

        if backend == "pi":
            from .pi_agent import PiRpcAgent
            agent: AgentBackend = PiRpcAgent(
                task_uri,
                callbacks=callbacks,
                provider=provider,
                model=model,
            )
        else:
            from .acp_agent import AcpAgent
            agent = AcpAgent(task_uri, callbacks=callbacks)

        self._agents[task_uri] = agent
        task = asyncio.create_task(agent.run(cwd=cwd), name=f"{backend}-{task_uri}")
        self._tasks[task_uri] = task

        try:
            await asyncio.wait_for(agent.ready.wait(), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("[%s] %s 启动超时", task_uri, backend)

        return agent

    def get(self, task_uri: str) -> AgentBackend | None:
        agent = self._agents.get(task_uri)
        if agent and agent.is_alive:
            return agent
        return None

    def list(self) -> list[AgentState]:
        return [
            a.state_snapshot()
            for a in self._agents.values()
            if a.is_alive
        ]

    def get_state(self, task_uri: str) -> AgentState | None:
        agent = self.get(task_uri)
        return agent.state_snapshot() if agent else None

    async def stop(self, task_uri: str) -> None:
        agent = self._agents.pop(task_uri, None)
        task = self._tasks.pop(task_uri, None)
        if agent:
            await agent.stop()
        if task and not task.done():
            task.cancel()

    async def stop_all(self) -> None:
        for uri in list(self._agents.keys()):
            await self.stop(uri)
