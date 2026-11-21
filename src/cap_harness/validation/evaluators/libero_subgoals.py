"""Host-only sub-goal witness for LIBERO-Pro: one record per BDDL goal conjunct.

LIBERO's success predicate is the conjunction of the task's BDDL goal predicates
(``parsed_problem["goal_state"]``). This witness evaluates each conjunct after every step and
records when it first held, when it last changed, how often it flipped and whether it holds at
the end, so a run's progress can be graded per sub-goal rather than only as success or failure.
For every ``(Close X)`` goal it also tracks ``(Open X)`` as an intermediate milestone (not part of
success): closing a drawer the task needed opened says nothing about whether it was ever opened.

Only booleans and step indices leave this module; generated programs never see it.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

SCHEMA_VERSION = 1


def _problem_env(native_env: Any) -> Any:
    """Walk wrapper layers to the BDDL problem environment."""
    env = native_env
    for _ in range(4):
        if hasattr(env, "parsed_problem") and hasattr(env, "_eval_predicate"):
            return env
        env = getattr(env, "env", None)
        if env is None:
            break
    raise RuntimeError("LIBERO environment exposes no BDDL goal predicates")


def has_goal_predicates(native_env: Any) -> bool:
    try:
        _problem_env(native_env)
    except RuntimeError:
        return False
    return True


def _label(state: Any) -> str:
    return "(" + " ".join(str(part) for part in state) + ")"


class LiberoSubgoalWitness:
    """Track each BDDL goal conjunct of one LIBERO episode."""

    def __init__(self, task_ref: str, native_env: Any) -> None:
        self.task_ref = task_ref
        self._env = _problem_env(native_env)
        goals = tuple(tuple(state) for state in self._env.parsed_problem["goal_state"])
        if not goals:
            raise ValueError(f"{task_ref} has an empty goal")
        extra = tuple(
            ("open", *state[1:])
            for state in goals
            if str(state[0]).lower() == "close" and len(state) == 2
        )
        self._goals = extra + goals
        self._is_goal = (False,) * len(extra) + (True,) * len(goals)
        n = len(self._goals)
        self._step_index = 0
        self._current: list[bool] = [False] * n
        self._first_true: list[int | None] = [None] * n
        self._last_change: list[int | None] = [None] * n
        self._flips: list[int] = [0] * n
        self._all_first_true: int | None = None
        self.errors: list[str] = []
        self._evaluate()  # state at reset, step 0

    def _evaluate(self) -> None:
        for index, state in enumerate(self._goals):
            try:
                value = bool(self._env._eval_predicate(state))
            except Exception as exc:  # keep the episode alive; report the failure
                self.errors.append(f"{_label(state)}: {type(exc).__name__}")
                continue
            if value != self._current[index]:
                self._flips[index] += 1
                self._last_change[index] = self._step_index
                self._current[index] = value
            if value and self._first_true[index] is None:
                self._first_true[index] = self._step_index
        if self._all_first_true is None and self._goal_success():
            self._all_first_true = self._step_index

    def _goal_success(self) -> bool:
        return all(v for v, g in zip(self._current, self._is_goal, strict=True) if g)

    def after_step(self, action: Any, result: Any) -> None:
        del action
        if not getattr(result, "ok", True):
            return
        self._step_index += 1
        self._evaluate()

    def evidence(self, *, final_native_success: bool | None = None) -> Mapping[str, object]:
        subgoals = tuple(
            MappingProxyType(
                {
                    "predicate": _label(state),
                    "goal": self._is_goal[index],
                    "final": self._current[index],
                    "ever": self._first_true[index] is not None,
                    "first_true_step": self._first_true[index],
                    "last_change_step": self._last_change[index],
                    "flips": self._flips[index],
                }
            )
            for index, state in enumerate(self._goals)
        )
        reached = sum(1 for item in subgoals if item["final"] and item["goal"])
        return MappingProxyType(
            {
                "schema_version": SCHEMA_VERSION,
                "task": self.task_ref,
                "protocol_success": self._goal_success() and not self.errors,
                "subgoals": subgoals,
                "subgoals_final": reached,
                "subgoals_total": sum(self._is_goal),
                "all_first_true_step": self._all_first_true,
                "steps_observed": self._step_index,
                "final_native_success": final_native_success,
                "evaluator_errors": tuple(self.errors),
            }
        )
