import json
from fractions import Fraction

from plan.schedule import FrozenSchedule, FrozenScheduleStage, validate_schedule


def encode_schedule_payload(schedule: FrozenSchedule) -> str:
    return json.dumps({
        'plan_id': schedule.plan_id,
        'stages': [[stage.name, str(stage.ratio), stage.steps] for stage in schedule.stages],
    }, ensure_ascii=False)


def decode_schedule_payload(schedule_id: str, payload: str) -> FrozenSchedule:
    try:
        value = json.loads(payload)
        stages = tuple(
            FrozenScheduleStage(entry[0], Fraction(entry[1]), entry[2])
            for entry in value['stages']
        )
        return validate_schedule(FrozenSchedule(schedule_id, value['plan_id'], stages))
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as error:
        raise ValueError(f'invalid archived schedule payload for {schedule_id!r}') from error
