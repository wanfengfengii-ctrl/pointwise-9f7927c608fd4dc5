from collections.abc import Callable
from uuid import uuid4

from analysis.occupation import forecast_occupation
from analysis.schedule_occupation import schedule_occupation
from archive.catalog import HandoverArchive
from archive.plan_store import PlanStore
from archive.report_store import ReportStore
from archive.schedule_report_store import ScheduleReportStore
from archive.schedule_store import ScheduleStore
from publication.encoding import encode_receipt, encode_report
from publication.receipt import IssueReceipt, make_receipt
from publication.report import OccupationReport, validate_report
from publication.schedule_encoding import encode_schedule_receipt, encode_schedule_report
from publication.schedule_report import ScheduleReport, validate_schedule_report


def issue_report(
    archive: HandoverArchive,
    plan_id: str,
    *,
    before_commit: Callable[[], None] | None = None,
) -> tuple[OccupationReport, IssueReceipt]:
    plan = PlanStore(archive).load(plan_id)
    draft = forecast_occupation(plan)
    if draft.plan_id != plan.plan_id or draft.stations != plan.stations:
        raise ValueError('occupation draft does not match the requested plan')
    report = validate_report(OccupationReport(f'report-{uuid4().hex}', draft.plan_id, draft.stations, draft.zero, draft.rare))
    receipt = make_receipt(report)
    ReportStore(archive).commit_issue(
        report.report_id,
        report.plan_id,
        encode_report(report),
        encode_receipt(receipt),
        before_commit=before_commit,
    )
    return report, receipt


def issue_schedule_report(
    archive: HandoverArchive,
    schedule_id: str,
    *,
    before_commit: Callable[[], None] | None = None,
) -> tuple[ScheduleReport, IssueReceipt]:
    """Issue the stored long-run occupations of a frozen cyclic schedule."""
    schedule = ScheduleStore(archive).load(schedule_id)
    plan = PlanStore(archive).load(schedule.plan_id)
    draft = schedule_occupation(plan, schedule)
    if draft.plan_id != plan.plan_id or draft.stations != plan.stations:
        raise ValueError('schedule occupation draft does not match the frozen plan')
    report = validate_schedule_report(ScheduleReport(
        f'report-{uuid4().hex}',
        draft.schedule_id,
        draft.plan_id,
        draft.stations,
        draft.stages,
        draft.stage_occupations,
        draft.round_occupation,
    ))
    receipt = make_receipt(report)
    ScheduleReportStore(archive).commit_issue(
        report.report_id,
        report.schedule_id,
        report.plan_id,
        encode_schedule_report(report),
        encode_schedule_receipt(receipt),
        before_commit=before_commit,
    )
    return report, receipt
