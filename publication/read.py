from archive.catalog import HandoverArchive
from archive.report_store import ReportStore
from archive.schedule_report_store import ScheduleReportStore
from publication.encoding import decode_receipt, decode_report
from publication.receipt import IssueReceipt, validate_receipt_binding
from publication.report import OccupationReport
from publication.schedule_encoding import decode_schedule_receipt, decode_schedule_report
from publication.schedule_report import ScheduleReport


def read_report(archive: HandoverArchive, report_id: str) -> tuple[OccupationReport, IssueReceipt]:
    indexed_plan_id, report_payload, receipt_payload = ReportStore(archive).load_issue(report_id)
    report = decode_report(report_payload)
    if report.report_id != report_id or report.plan_id != indexed_plan_id:
        raise ValueError('archived report does not match its index')
    receipt = decode_receipt(receipt_payload)
    validate_receipt_binding(report, receipt)
    return report, receipt


def read_schedule_report(archive: HandoverArchive, report_id: str) -> tuple[ScheduleReport, IssueReceipt]:
    """Return the archived schedule report and receipt without recomputing."""
    indexed_schedule_id, indexed_plan_id, report_payload, receipt_payload = ScheduleReportStore(archive).load_issue(report_id)
    report = decode_schedule_report(report_payload)
    if (
        report.report_id != report_id
        or report.schedule_id != indexed_schedule_id
        or report.plan_id != indexed_plan_id
    ):
        raise ValueError('archived schedule report does not match its index')
    receipt = decode_schedule_receipt(receipt_payload)
    validate_receipt_binding(report, receipt)
    return report, receipt
