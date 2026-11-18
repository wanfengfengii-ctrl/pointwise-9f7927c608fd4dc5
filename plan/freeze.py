from collections.abc import Iterable
from uuid import uuid4

from archive.catalog import HandoverArchive
from archive.plan_store import PlanStore
from archive.schedule_store import ScheduleStore
from plan.eligibility import check_eligibility
from plan.schedule import build_schedule
from plan.snapshot import FrozenPlan, FrozenRoute
from routing.revision_store import RevisionStore


def freeze_plan(source: RevisionStore, archive: HandoverArchive, revision_id: str) -> str:
    revision = source.get(revision_id)
    stations = tuple(station.name for station in revision.stations)
    check_eligibility(stations, revision.routes)
    routes = tuple(
        FrozenRoute(route.route_id, route.source, route.destination, route.base_probability, route.releases)
        for route in revision.routes
    )
    plan = FrozenPlan(f'plan-{uuid4().hex}', revision.revision_id, stations, revision.initial, routes)
    PlanStore(archive).save(plan)
    return plan.plan_id


def freeze_schedule(archive: HandoverArchive, plan_id: str, stages: Iterable) -> str:
    """Freeze an ordered cyclic schedule on an existing fixed plan."""
    plan = PlanStore(archive).load(plan_id)
    schedule = build_schedule(f'schedule-{uuid4().hex}', plan.plan_id, stages)
    ScheduleStore(archive).save(schedule)
    return schedule.schedule_id
