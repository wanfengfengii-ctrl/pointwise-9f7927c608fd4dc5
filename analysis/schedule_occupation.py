from dataclasses import dataclass
from fractions import Fraction

from analysis.long_run import (
    Matrix,
    long_run_distribution,
    matrix_multiply,
    matrix_power,
    matrix_power_sum,
    multiply_vector,
)
from analysis.transition import build_transition
from plan.schedule import FrozenSchedule
from plan.snapshot import FrozenPlan


@dataclass(frozen=True, slots=True)
class ScheduleOccupationDraft:
    schedule_id: str
    plan_id: str
    stations: tuple[str, ...]
    stages: tuple[tuple[str, Fraction, int], ...]
    stage_occupations: tuple[tuple[Fraction, ...], ...]
    round_occupation: tuple[Fraction, ...]


def _stage_matrix(plan: FrozenPlan, ratio: Fraction) -> Matrix:
    return build_transition(plan, ratio)


def _round_matrix(plan: FrozenPlan, stages) -> Matrix:
    times = sum(stage.steps for stage in stages)
    if times < 1:
        raise ValueError('a schedule must have at least one executed step')
    round_matrix = None
    for stage in stages:
        block = matrix_power(_stage_matrix(plan, stage.ratio), stage.steps)
        round_matrix = block if round_matrix is None else matrix_multiply(round_matrix, block)
    return round_matrix


def schedule_occupation(plan: FrozenPlan, schedule: FrozenSchedule) -> ScheduleOccupationDraft:
    """Compute stage and whole-round long-run occupations for the fixed plan.

    The round repeats forever.  ``long_run_distribution`` gives the Cesaro
    average distribution just before a round opens, starting from the plan's
    opening distribution; this is still the right base when the whole-round
    chain is reducible or periodic.  Within one round the ordered per-step
    matrices yield the distribution just before each executed step, which is
    averaged over the stage's own steps or over the whole round.
    """
    station_count = len(plan.stations)
    initial = tuple(Fraction(mass) for mass in plan.initial)
    current = long_run_distribution(_round_matrix(plan, schedule.stages), initial)

    stage_vectors = []
    total = [Fraction(0)] * station_count
    step_count = 0
    for stage in schedule.stages:
        step = _stage_matrix(plan, stage.ratio)
        sharing = matrix_power(step, stage.steps)
        # Share of this stage spent at each pre-step position, relative to the
        # round's long-run average opening distribution.
        stage_total = multiply_vector(current, matrix_power_sum(step, stage.steps))
        stage_vectors.append(tuple(value / stage.steps for value in stage_total))
        for index in range(station_count):
            total[index] += stage_total[index]
        current = multiply_vector(current, sharing)
        step_count += stage.steps
    round_vector = tuple(value / step_count for value in total)
    return ScheduleOccupationDraft(
        schedule.schedule_id,
        plan.plan_id,
        plan.stations,
        tuple((stage.name, stage.ratio, stage.steps) for stage in schedule.stages),
        tuple(stage_vectors),
        round_vector,
    )
