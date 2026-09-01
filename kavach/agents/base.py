from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class Agent(Generic[T]):
    agent_id: str
    max_steps: int = 20

    def step(self, state: T) -> T:
        raise NotImplementedError
