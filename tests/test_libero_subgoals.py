from types import SimpleNamespace

from cap_harness.validation.evaluators.libero_subgoals import (
    LiberoSubgoalWitness,
    has_goal_predicates,
)


class _Problem:
    def __init__(self, goal):
        self.parsed_problem = {"goal_state": goal}
        self.truth = {}

    def _eval_predicate(self, state):
        return self.truth.get(tuple(state), False)


def _ok():
    return SimpleNamespace(ok=True)


def test_tracks_each_conjunct_and_open_before_close():
    problem = _Problem([["Close", "drawer"], ["In", "bowl", "drawer"]])
    native = SimpleNamespace(env=problem)
    assert has_goal_predicates(native)
    witness = LiberoSubgoalWitness("suite:3", native)

    problem.truth[("open", "drawer")] = True
    witness.after_step(None, _ok())  # step 1: drawer open
    problem.truth[("In", "bowl", "drawer")] = True
    witness.after_step(None, _ok())  # step 2: bowl in
    problem.truth[("open", "drawer")] = False
    problem.truth[("Close", "drawer")] = True
    witness.after_step(None, _ok())  # step 3: closed -> success

    ev = witness.evidence(final_native_success=True)
    by = {s["predicate"]: s for s in ev["subgoals"]}
    assert by["(open drawer)"]["goal"] is False
    assert by["(open drawer)"]["first_true_step"] == 1
    assert by["(In bowl drawer)"]["first_true_step"] == 2
    assert by["(Close drawer)"]["final"] is True
    assert ev["protocol_success"] is True
    assert ev["subgoals_final"] == 2 and ev["subgoals_total"] == 2
    assert ev["all_first_true_step"] == 3


def test_failed_steps_are_not_counted_and_fakes_are_skipped():
    problem = _Problem([["In", "a", "b"]])
    witness = LiberoSubgoalWitness("s:0", problem)
    witness.after_step(None, SimpleNamespace(ok=False))
    assert witness.evidence()["steps_observed"] == 0
    assert witness.evidence()["protocol_success"] is False
    assert not has_goal_predicates(SimpleNamespace())
