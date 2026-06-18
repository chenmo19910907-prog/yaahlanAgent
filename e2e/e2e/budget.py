"""单步时间预算（默认 3s）。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepBudget:
    """一步识别→思考→执行的毫秒预算与分项上限。"""

    step_budget_ms: int = 3000
    perceive_ms: int = 1400
    think_ms: int = 100
    act_ms: int = 600
    post_act_ms: int = 800
    subprocess_timeout_s: float = 2.5
    ui_limit: int = 30
    post_act_mode: str = "activity"  # activity | wait_observe | skip
    post_act_wait_sec: float = 0.5

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> StepBudget:
        cfg = config if isinstance(config, dict) else {}
        loop = cfg.get("loop") if isinstance(cfg.get("loop"), dict) else {}
        timing = loop.get("timing") if isinstance(loop.get("timing"), dict) else {}
        perceive = loop.get("perceive") if isinstance(loop.get("perceive"), dict) else {}
        post = loop.get("postAct") if isinstance(loop.get("postAct"), dict) else {}

        return cls(
            step_budget_ms=int(timing.get("stepBudgetMs") or 3000),
            perceive_ms=int(timing.get("perceiveMs") or 1400),
            think_ms=int(timing.get("thinkMs") or 100),
            act_ms=int(timing.get("actMs") or 600),
            post_act_ms=int(timing.get("postActMs") or 800),
            subprocess_timeout_s=float(timing.get("subprocessTimeoutSec") or 2.5),
            ui_limit=int(perceive.get("uiLimit") or 30),
            post_act_mode=str(post.get("mode") or "activity"),
            post_act_wait_sec=float(post.get("maxWaitSec") or 0.5),
        )


@dataclass
class StepTimer:
    budget: StepBudget
    started_at: float = field(default_factory=time.perf_counter)
    phases: dict[str, int] = field(default_factory=dict)

    def mark(self, phase: str, elapsed_ms: int) -> None:
        self.phases[phase] = elapsed_ms

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started_at) * 1000)

    def remaining_ms(self) -> int:
        return max(0, self.budget.step_budget_ms - self.elapsed_ms())

    def to_dict(self) -> dict[str, Any]:
        total = self.elapsed_ms()
        return {
            **self.phases,
            "total": total,
            "budget": self.budget.step_budget_ms,
            "withinBudget": total <= self.budget.step_budget_ms,
        }
