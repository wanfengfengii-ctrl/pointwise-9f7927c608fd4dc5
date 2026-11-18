from dataclasses import dataclass
from fractions import Fraction

from plan.probability import validate_ratio
from routing.stations import RationalInput, ordered_items, validate_identity


@dataclass(frozen=True, slots=True)
class FrozenScheduleStage:
    name: str
    ratio: Fraction
    steps: int


@dataclass(frozen=True, slots=True)
class FrozenSchedule:
    schedule_id: str
    plan_id: str
    stages: tuple[FrozenScheduleStage, ...]


def validate_steps(value: object, label: str = 'stage steps') -> int:
    if isinstance(value, bool) or type(value) is not int:
        raise ValueError(f'{label} must be a non-boolean positive integer')
    if value < 1:
        raise ValueError(f'{label} must be a non-boolean positive integer')
    return value


def validate_stage(value: object) -> FrozenScheduleStage:
    if not isinstance(value, FrozenScheduleStage):
        raise ValueError('each frozen schedule stage must be a FrozenScheduleStage')
    name = validate_identity(value.name, 'stage name')
    ratio = validate_ratio(value.ratio)
    return FrozenScheduleStage(name, ratio, validate_steps(value.steps))


def validate_schedule(schedule: FrozenSchedule) -> FrozenSchedule:
    """Validate and canonicalize a frozen cyclic inspection schedule."""
    if not isinstance(schedule, FrozenSchedule):
        raise ValueError('expected a FrozenSchedule')
    schedule_id = validate_identity(schedule.schedule_id, 'schedule identity')
    plan_id = validate_identity(schedule.plan_id, 'plan identity')
    entries = ordered_items(schedule.stages, 'schedule stages')
    if not entries:
        raise ValueError('a schedule must have at least one stage')
    names = set()
    stages = []
    for entry in entries:
        stage = validate_stage(entry)
        if stage.name in names:
            raise ValueError(f'duplicate stage {stage.name!r}')
        names.add(stage.name)
        stages.append(stage)
    return FrozenSchedule(schedule_id, plan_id, tuple(stages))


def build_schedule(schedule_id: str, plan_id: str, stages) -> FrozenSchedule:
    """Validate caller input and freeze it into an ordered stage tuple."""
    identifier = validate_identity(schedule_id, 'schedule identity')
    plan = validate_identity(plan_id, 'plan identity')
    entries = ordered_items(stages, 'schedule stages')
    if not entries:
        raise ValueError('a schedule must have at least one stage')
    normalized = []
    names = set()
    for entry in entries:
        if isinstance(entry, FrozenScheduleStage):
            stage = validate_stage(entry)
        else:
            if isinstance(entry, (str, bytes)):
                raise ValueError('each schedule stage must be a (name, ratio, steps) triple')
            item = ordered_items(entry, 'schedule stage')
            if len(item) != 3:
                raise ValueError('each schedule stage must be a (name, ratio, steps) triple')
            name = validate_identity(item[0], 'stage name')
            ratio: RationalInput = item[1]
            stage = FrozenScheduleStage(name, validate_ratio(ratio), validate_steps(item[2]))
        if stage.name in names:
            raise ValueError(f'duplicate stage {stage.name!r}')
        names.add(stage.name)
        normalized.append(stage)
    return FrozenSchedule(identifier, plan, tuple(normalized))
