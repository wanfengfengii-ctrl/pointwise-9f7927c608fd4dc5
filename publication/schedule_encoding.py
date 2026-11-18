import json
from fractions import Fraction

from publication.receipt import IssueReceipt
from publication.schedule_report import ScheduleReport, validate_schedule_report
from routing.stations import validate_identity


def encode_schedule_report(report: ScheduleReport) -> str:
    report = validate_schedule_report(report)
    return json.dumps({
        'report_id': report.report_id,
        'schedule_id': report.schedule_id,
        'plan_id': report.plan_id,
        'stations': list(report.stations),
        'stages': [[name, str(ratio), steps] for name, ratio, steps in report.stages],
        'stage_occupations': [[str(mass) for mass in vector] for vector in report.stage_occupations],
        'round_occupation': [str(mass) for mass in report.round_occupation],
    }, ensure_ascii=False)


def decode_schedule_report(payload: str) -> ScheduleReport:
    try:
        value = json.loads(payload)
        return validate_schedule_report(ScheduleReport(
            value['report_id'],
            value['schedule_id'],
            value['plan_id'],
            tuple(value['stations']),
            tuple((name, Fraction(ratio), steps) for name, ratio, steps in value['stages']),
            tuple(tuple(Fraction(mass) for mass in vector) for vector in value['stage_occupations']),
            tuple(Fraction(mass) for mass in value['round_occupation']),
        ))
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as error:
        raise ValueError('invalid archived schedule report') from error


def encode_schedule_receipt(receipt: IssueReceipt) -> str:
    return json.dumps({
        'report_id': validate_identity(receipt.report_id, 'receipt report identity'),
        'plan_id': validate_identity(receipt.plan_id, 'receipt plan identity'),
    }, ensure_ascii=False)


def decode_schedule_receipt(payload: str) -> IssueReceipt:
    try:
        value = json.loads(payload)
        return IssueReceipt(
            validate_identity(value['report_id'], 'receipt report identity'),
            validate_identity(value['plan_id'], 'receipt plan identity'),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('invalid archived issue receipt') from error
