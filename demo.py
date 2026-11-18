import json
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.catalog import HandoverArchive
from plan.audit import audit_plan
from plan.freeze import freeze_plan, freeze_schedule
from publication.issue import issue_report, issue_schedule_report
from publication.read import read_report, read_schedule_report
from routing.intake import record_revision
from routing.revision_store import RevisionStore
from routing.routes import RouteRule
from schedule_examples import ABA, ABB, SWAP_ROUTES, prepare_swap_plan


EXAMPLES = Path(__file__).resolve().parent / 'examples'


def load_shift(name):
    return json.loads((EXAMPLES / name).read_text(encoding='utf-8'))


def prepare_shift(source, archive, shift):
    revision_id = record_revision(
        source, shift['stations'], shift['initial'], tuple(RouteRule(**route) for route in shift['routes']),
    )
    plan_id = freeze_plan(source, archive, revision_id)
    return revision_id, audit_plan(archive, plan_id, shift['audit_ratio'])


def audit_columns(audit):
    return {
        'routes': [[row.route_id, str(row.probability)] for row in audit.routes],
        'remaining': [[station, str(mass)] for station, mass in zip(audit.stations, audit.remaining, strict=True)],
    }


def report_columns(report):
    return {
        'stations': list(report.stations),
        'zero': [str(value) for value in report.zero],
        'rare': [str(value) for value in report.rare],
    }


def schedule_columns(report):
    return {
        'stations': list(report.stations),
        'stages': [[name, str(ratio), steps] for name, ratio, steps in report.stages],
        'stage_occupations': [[str(mass) for mass in vector] for vector in report.stage_occupations],
        'round_occupation': [str(mass) for mass in report.round_occupation],
    }


def check_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f'{label} expected {expected!r}, received {actual!r}')


def check_schedule(report, receipt, schedule_id, plan_id, expected_round, expected_stages):
    check_equal(report.schedule_id, schedule_id, 'schedule identity')
    check_equal(report.plan_id, plan_id, 'schedule plan identity')
    check_equal(report.stations, ('A', 'B'), 'schedule stations')
    check_equal(report.round_occupation, expected_round, 'schedule round occupation')
    check_equal(report.stage_occupations, expected_stages, 'schedule stage occupations')
    check_equal((receipt.report_id, receipt.plan_id), (report.report_id, report.plan_id), 'schedule receipt binding')
    for vector in report.stage_occupations + (report.round_occupation,):
        if any(not isinstance(value, Fraction) for value in vector) or sum(vector) != 1:
            raise AssertionError(f'schedule occupation vector is not an exact unit distribution: {vector!r}')


def main():
    day = load_shift('day.json')
    correction = load_shift('correction.json')
    with TemporaryDirectory(prefix='repair-handover-') as temporary:
        source_path = Path(temporary) / 'routing.sqlite'
        archive_path = Path(temporary) / 'handover.sqlite'
        with RevisionStore(source_path) as source, HandoverArchive.open(archive_path) as archive:
            source.initialize()
            archive.initialize()
            first_revision, day_audit = prepare_shift(source, archive, day)
            day_issue = issue_report(archive, day_audit.plan_id)
            correction_revision, correction_audit = prepare_shift(source, archive, correction)
            correction_issue = issue_report(archive, correction_audit.plan_id)
            if first_revision == correction_revision or day_issue[0].report_id == correction_issue[0].report_id:
                raise AssertionError('the two shifts must have separate archival identities')

            swap_plan = prepare_swap_plan(source, archive)
            first_schedule = freeze_schedule(archive, swap_plan, ABA)
            second_schedule = freeze_schedule(archive, swap_plan, ABB)
            record_revision(source, ('A', 'B'), (0, 1), SWAP_ROUTES)
        source_path.rename(source_path.with_suffix('.offline'))
        with HandoverArchive.open(archive_path) as archive:
            night_audit = audit_plan(archive, day_audit.plan_id, day['audit_ratio'])
            night_issue = read_report(archive, day_issue[0].report_id)
            check_equal(read_report(archive, correction_issue[0].report_id), correction_issue, 'corrected issue')
            check_equal(night_audit, day_audit, 'original audit after reopening')
            check_equal(night_issue, day_issue, 'original issue and receipt after reopening')
            first_issue = issue_schedule_report(archive, first_schedule)
            second_issue = issue_schedule_report(archive, second_schedule)
        with HandoverArchive.open(archive_path) as archive:
            night_first = read_schedule_report(archive, first_issue[0].report_id)
            night_second = read_schedule_report(archive, second_issue[0].report_id)
            check_equal(night_first, first_issue, 'first schedule issue after reopening')
            check_equal(night_second, second_issue, 'second schedule issue after reopening')
            check_equal(night_first[0].stage_occupations, first_issue[0].stage_occupations, 'stored stage occupations')
            check_equal(night_second[0].round_occupation, second_issue[0].round_occupation, 'stored round occupation')

        expected_audit = {'routes': [['outbound', '1/8'], ['return', '1/32']], 'remaining': [['A', '7/8'], ['B', '31/32']]}
        expected_report = {'stations': ['A', 'B'], 'zero': ['1', '0'], 'rare': ['0', '1']}
        actual_audit, offline_audit = audit_columns(day_audit), audit_columns(night_audit)
        actual_report, offline_report = report_columns(day_issue[0]), report_columns(night_issue[0])
        check_equal(actual_audit, expected_audit, 'day-shift audit')
        check_equal(actual_report, expected_report, 'day-shift occupation')
        check_equal(report_columns(correction_issue[0]), {'stations': ['A', 'B'], 'zero': ['1', '0'], 'rare': ['1', '0']}, 'corrected occupation')
        check_equal((night_issue[1].report_id, night_issue[1].plan_id), (night_issue[0].report_id, night_audit.plan_id), 'night-shift receipt binding')

        expected_first_stages = ((Fraction(1), Fraction(0)), (Fraction(0), Fraction(1)), (Fraction(1), Fraction(0)))
        expected_second_stages = ((Fraction(1), Fraction(0)), (Fraction(0), Fraction(1)), (Fraction(0), Fraction(1)))
        expected_first_round = (Fraction(2, 3), Fraction(1, 3))
        expected_second_round = (Fraction(1, 3), Fraction(2, 3))
        first_report, first_receipt = first_issue
        second_report, second_receipt = second_issue
        check_schedule(first_report, first_receipt, first_schedule, swap_plan, expected_first_round, expected_first_stages)
        check_schedule(second_report, second_receipt, second_schedule, swap_plan, expected_second_round, expected_second_stages)
        check_equal(night_first[0].stage_occupations, first_report.stage_occupations, 'first schedule stored stages')
        check_equal(night_second[0].stage_occupations, second_report.stage_occupations, 'second schedule stored stages')
        if first_report.round_occupation == second_report.round_occupation:
            raise AssertionError('the two schedules must differ inside the round')

        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'v_reopen.first_task_quarter',
            'input': {'original': day, 'correction': correction, 'source_disconnected': not source_path.exists()},
            'expected': {'audit': expected_audit, 'report': expected_report},
            'actual': {'audit': actual_audit, 'report': actual_report},
            'downstream_expected': {'audit': expected_audit, 'report': expected_report, 'original_receipt': True},
            'downstream_actual': {'audit': offline_audit, 'report': offline_report, 'original_receipt': night_issue[1] == day_issue[1]},
            'code_paths': ['routing/intake.py', 'plan/freeze.py', 'plan/audit.py', 'analysis/occupation.py', 'analysis/rare_limit.py', 'publication/issue.py', 'publication/read.py', 'archive/report_store.py'],
            'oracle': 'Substitute x=1/4 into x/2 and x squared over 2. At x=0 A retains the opening mass. Positive-ratio flow balance gives B a mass of 1/(1+x).',
        }, ensure_ascii=False, sort_keys=True))
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'v_schedule.cyclic_round_in_round',
            'input': {
                'plan_stations': ['A', 'B'], 'initial': ['1', '0'],
                'schedules': {'ABA': [[name, str(ratio), steps] for name, ratio, steps in ABA],
                              'ABB': [[name, str(ratio), steps] for name, ratio, steps in ABB]},
                'source_disconnected': not source_path.exists(),
            },
            'expected': {
                'ABA': {'stage_occupations': [['1', '0'], ['0', '1'], ['1', '0']], 'round_occupation': ['2/3', '1/3']},
                'ABB': {'stage_occupations': [['1', '0'], ['0', '1'], ['0', '1']], 'round_occupation': ['1/3', '2/3']},
            },
            'actual': {'ABA': schedule_columns(first_report), 'ABB': schedule_columns(second_report)},
            'downstream_expected': {'ABA': schedule_columns(first_report), 'ABB': schedule_columns(second_report), 'reopened_issue_equal': True},
            'downstream_actual': {'ABA': schedule_columns(night_first[0]), 'ABB': schedule_columns(night_second[0]),
                                  'reopened_issue_equal': (night_first, night_second) == (first_issue, second_issue)},
            'code_paths': ['plan/schedule.py', 'archive/schedule_store.py', 'analysis/schedule_occupation.py',
                           'analysis/long_run.py', 'plan/freeze.py', 'publication/issue.py', 'publication/read.py',
                           'archive/schedule_report_store.py'],
            'oracle': 'Both rounds return to A. The pre-step distribution restarts from the opening mass, so ABA spends two of three steps at A and ABB one of three at A.',
        }, ensure_ascii=False, sort_keys=True))
        print(f'夜班凭 {night_issue[0].report_id} 领取原报告和回执。')
        for station, zero, rare in zip(night_issue[0].stations, night_issue[0].zero, night_issue[0].rare, strict=True):
            print(f'{station} 工位完全关闭占比 {zero}，微量放行极限占比 {rare}')
        for report, receipt in (night_first, night_second):
            stage_text = ', '.join(
                f'{name}={tuple(map(str, vector))}' for (name, _, _), vector in zip(report.stages, report.stage_occupations, strict=True)
            )
            print(f'日程 {report.schedule_id} 报告 {receipt.report_id}：阶段占用 {stage_text}；整轮占用 {tuple(map(str, report.round_occupation))}')


if __name__ == '__main__':
    main()
