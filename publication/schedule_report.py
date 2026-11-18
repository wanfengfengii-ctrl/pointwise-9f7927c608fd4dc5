from dataclasses import dataclass
from fractions import Fraction

from routing.stations import exact_fraction, validate_identity, validate_stations


@dataclass(frozen=True, slots=True)
class ScheduleReport:
    report_id: str
    schedule_id: str
    plan_id: str
    stations: tuple[str, ...]
    stages: tuple[tuple[str, Fraction, int], ...]
    stage_occupations: tuple[tuple[Fraction, ...], ...]
    round_occupation: tuple[Fraction, ...]


def _validate_steps(value: object) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 1:
        raise ValueError('stage steps must be a non-boolean positive integer')
    return value


def _validate_distribution(vector: object, station_names: tuple[str, ...], label: str) -> tuple[Fraction, ...]:
    if not isinstance(vector, tuple):
        raise ValueError(f'{label} must be a tuple in station order')
    if len(vector) != len(station_names):
        raise ValueError(f'{label} must have one entry per station')
    masses = tuple(exact_fraction(value, f'{label} entry') for value in vector)
    if any(mass < 0 for mass in masses) or sum(masses) != 1:
        raise ValueError(f'{label} must be nonnegative and sum to one')
    return masses


def validate_schedule_report(report: ScheduleReport) -> ScheduleReport:
    if not isinstance(report, ScheduleReport):
        raise ValueError('expected a ScheduleReport')
    report_id = validate_identity(report.report_id, 'report identity')
    schedule_id = validate_identity(report.schedule_id, 'schedule identity')
    plan_id = validate_identity(report.plan_id, 'plan identity')
    stations = validate_stations(report.stations)
    station_names = tuple(station.name for station in stations)
    if not 2 <= len(station_names) <= 6:
        raise ValueError('a schedule report must have two to six stations')
    if not isinstance(report.stages, tuple) or not report.stages:
        raise ValueError('a schedule report must carry an ordered nonempty stage tuple')
    names = set()
    stages = []
    for entry in report.stages:
        if not isinstance(entry, tuple) or len(entry) != 3:
            raise ValueError('each reported stage must be a (name, ratio, steps) triple')
        name = validate_identity(entry[0], 'stage name')
        if name in names:
            raise ValueError(f'duplicate stage {name!r}')
        names.add(name)
        ratio = exact_fraction(entry[1], f'ratio of stage {name!r}')
        if not 0 <= ratio <= 1:
            raise ValueError(f'ratio of stage {name!r} must be between zero and one')
        stages.append((name, ratio, _validate_steps(entry[2])))
    if not isinstance(report.stage_occupations, tuple) or len(report.stage_occupations) != len(stages):
        raise ValueError('stage occupations must match the reported stages')
    stage_occupations = tuple(
        _validate_distribution(vector, station_names, f'occupation of stage {stage[0]!r}')
        for stage, vector in zip(stages, report.stage_occupations, strict=True)
    )
    round_occupation = _validate_distribution(report.round_occupation, station_names, 'round occupation')
    return ScheduleReport(
        report_id,
        schedule_id,
        plan_id,
        station_names,
        tuple(stages),
        stage_occupations,
        round_occupation,
    )
