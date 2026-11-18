import json
from dataclasses import replace
from fractions import Fraction as F

from analysis.schedule_occupation import schedule_occupation
from archive.catalog import HandoverArchive
from archive.plan_store import PlanStore
from archive.schedule_store import ScheduleStore
from plan.freeze import freeze_plan, freeze_schedule
from plan.schedule import build_schedule
from publication.issue import issue_report, issue_schedule_report
from publication.read import read_report, read_schedule_report
from publication.schedule_report import validate_schedule_report
from routing.intake import record_revision
from routing.routes import RouteRule
from schedule_examples import (
    ABA,
    ABB,
    DOUBLE_SWAP,
    SINGLE_SWAP,
    SWAP_ROUTES,
    WEIGHTED,
    ZERO_SPLIT,
    prepare_split_plan,
    prepare_swap_plan,
)
from tests.support import LineTestCase


class InjectedCommitFailure(RuntimeError):
    pass


class ScheduleTests(LineTestCase):
    def prepare_swap(self):
        return prepare_swap_plan(self.source, self.archive)

    def issue(self, schedule_id):
        return issue_schedule_report(self.archive, schedule_id)

    def schedule_counts(self, archive=None):
        connection = (self.archive if archive is None else archive).connection
        return connection.execute('''
            SELECT (SELECT count(*) FROM schedules),
                   (SELECT count(*) FROM schedule_reports),
                   (SELECT count(*) FROM schedule_receipts)
        ''').fetchone()

    def test_swap_examples(self):
        plan_id = self.prepare_swap()
        cases = (
            (ABA, ((1, 0), (0, 1), (1, 0)), (F(2, 3), F(1, 3))),
            (ABB, ((1, 0), (0, 1), (0, 1)), (F(1, 3), F(2, 3))),
            (WEIGHTED, ((1, 0), (0, 1), (1, 0)), (F(3, 4), F(1, 4))),
            (SINGLE_SWAP, ((F(1, 2), F(1, 2)),), (F(1, 2), F(1, 2))),
            (DOUBLE_SWAP, ((F(1, 2), F(1, 2)),), (F(1, 2), F(1, 2))),
        )
        for stages, expected_stages, expected_round in cases:
            with self.subTest(stages=stages):
                schedule_id = freeze_schedule(self.archive, plan_id, stages)
                report, receipt = self.issue(schedule_id)
                self.assertEqual(report.schedule_id, schedule_id)
                self.assertEqual(report.plan_id, plan_id)
                self.assertEqual(report.stations, ('A', 'B'))
                self.assertEqual(report.stage_occupations, tuple(tuple(F(value) for value in vector) for vector in expected_stages))
                self.assertEqual(report.round_occupation, expected_round)
                self.assertEqual(tuple(entry[2] for entry in report.stages), tuple(stage[2] for stage in stages))
                self.assertEqual((receipt.report_id, receipt.plan_id), (report.report_id, report.plan_id))

    def test_round_vs_in_round_occupancy(self):
        # ABA and ABB both return to A at the round boundary but differ inside.
        plan_id = self.prepare_swap()
        first = freeze_schedule(self.archive, plan_id, ABA)
        second = freeze_schedule(self.archive, plan_id, ABB)
        first_report, _ = self.issue(first)
        second_report, _ = self.issue(second)
        self.assertNotEqual(first_report.round_occupation, second_report.round_occupation)
        self.assertEqual(first_report.stage_occupations, ((F(1), F(0)), (F(0), F(1)), (F(1), F(0))))
        self.assertEqual(second_report.stage_occupations, ((F(1), F(0)), (F(0), F(1)), (F(0), F(1))))
        for report in (first_report, second_report):
            self.assertEqual(sum(report.round_occupation), 1)
            for vector in report.stage_occupations:
                self.assertEqual(sum(vector), 1)

    def test_zero_split(self):
        plan_id = prepare_split_plan(self.source, self.archive)
        schedule_id = freeze_schedule(self.archive, plan_id, ZERO_SPLIT)
        report, receipt = self.issue(schedule_id)
        expected = (F(0), F(1, 3), F(2, 3))
        self.assertEqual(report.stations, ('A', 'B', 'C'))
        self.assertEqual(report.stage_occupations, (expected, expected))
        self.assertEqual(report.round_occupation, expected)
        self.assertEqual(read_schedule_report(self.archive, report.report_id), (report, receipt))

    def test_round_weighting(self):
        # Stage averages treat each stage equally; the round average weights by steps.
        plan_id = self.prepare_swap()
        report, _ = self.issue(freeze_schedule(self.archive, plan_id, WEIGHTED))
        self.assertEqual(report.stage_occupations, ((F(1), F(0)), (F(0), F(1)), (F(1), F(0))))
        self.assertEqual(report.round_occupation, (F(3, 4), F(1, 4)))
        self.assertEqual(tuple(entry[2] for entry in report.stages), (1, 1, 2))

    def test_schedule_frozen_on_plan_and_input_mutation(self):
        plan_id = self.prepare_swap()
        stages = [['transfer', 1, 1], ['return', 1, 1], ['observe', 0, 1]]
        schedule_id = freeze_schedule(self.archive, plan_id, stages)
        stages[0][0] = 'mutated'
        stages.append(['extra', 0, 1])
        frozen = ScheduleStore(self.archive).load(schedule_id)
        self.assertEqual(frozen.plan_id, plan_id)
        self.assertEqual(tuple((stage.name, stage.ratio, stage.steps) for stage in frozen.stages), (
            ('transfer', F(1), 1), ('return', F(1), 1), ('observe', F(0), 1),
        ))
        report, _ = self.issue(schedule_id)
        self.assertEqual(tuple(entry[0] for entry in report.stages), ('transfer', 'return', 'observe'))

    def test_input_canonicalization(self):
        plan_id = self.prepare_swap()
        schedule_id = freeze_schedule(self.archive, plan_id, (
            ('first', '1/2', 2), ('second', F(3, 4), 1), ('third', 0, 5),
        ))
        frozen = ScheduleStore(self.archive).load(schedule_id)
        self.assertEqual(tuple((stage.name, stage.ratio) for stage in frozen.stages), (
            ('first', F(1, 2)), ('second', F(3, 4)), ('third', F(0)),
        ))
        self.assertEqual(tuple(stage.steps for stage in frozen.stages), (2, 1, 5))

    def test_invalid_schedule_inputs(self):
        plan_id = self.prepare_swap()
        baseline = self.archive_counts()
        cases = {
            'empty': (),
            'bare string': 'ABA',
            'one field': (('transfer',),),
            'four fields': (('transfer', 1, 1, 2),),
            'blank name': (('  ', 1, 1),),
            'non string name': ((None, 1, 1),),
            'duplicate name': (('same', 1, 1), ('same', 0, 1)),
            'ratio above one': (('a', '5/4', 1),),
            'negative ratio': (('a', '-1/4', 1),),
            'float ratio': (('a', 0.5, 1),),
            'boolean ratio': (('a', True, 1),),
            'zero steps': (('a', 1, 0),),
            'negative steps': (('a', 1, -1),),
            'boolean steps': (('a', 1, True),),
            'float steps': (('a', 1, 1.0),),
            'none steps': (('a', 1, None),),
        }
        for label, stages in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    freeze_schedule(self.archive, plan_id, stages)
                self.assertEqual(self.archive_counts(), baseline)
                self.assertEqual(self.schedule_counts(), (0, 0, 0))
        self.assertEqual(self.archive_counts(), (1, 0, 0))

    def test_unknown_schedule_and_plan(self):
        plan_id = self.prepare_swap()
        with self.assertRaises(KeyError):
            freeze_schedule(self.archive, 'missing-plan', ABA)
        self.assertEqual(self.schedule_counts(), (0, 0, 0))
        schedule_id = freeze_schedule(self.archive, plan_id, ABA)
        with self.assertRaises(KeyError):
            self.issue('missing-schedule')
        self.assertEqual(self.schedule_counts(), (1, 0, 0))
        with self.assertRaises(KeyError):
            read_schedule_report(self.archive, 'missing-report')
        self.assertEqual(self.schedule_counts(), (1, 0, 0))
        for bad in ('', '   ', None):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                read_schedule_report(self.archive, bad)
        self.assertEqual(schedule_id, ScheduleStore(self.archive).load(schedule_id).schedule_id)

    def test_reopen_and_corrected_source(self):
        plan_id = self.prepare_swap()
        schedule_id = freeze_schedule(self.archive, plan_id, ABA)
        issued = self.issue(schedule_id)
        record_revision(self.source, ('A', 'B'), (0, 1), SWAP_ROUTES)
        self.disconnect_source()
        self.reopen_archive()
        self.assertFalse(self.source_path.exists())
        received = read_schedule_report(self.archive, issued[0].report_id)
        self.assertEqual(received, issued)
        self.assertEqual(received[0].stage_occupations, ((F(1), F(0)), (F(0), F(1)), (F(1), F(0))))
        self.assertEqual(received[0].round_occupation, (F(2, 3), F(1, 3)))
        self.assertEqual((received[1].report_id, received[1].plan_id), (received[0].report_id, received[0].plan_id))
        reissued = issue_schedule_report(self.archive, schedule_id)
        self.assertEqual(reissued[0].stage_occupations, issued[0].stage_occupations)
        self.assertEqual(reissued[0].round_occupation, issued[0].round_occupation)
        self.assertEqual(read_schedule_report(self.archive, reissued[0].report_id), reissued)

    def test_read_is_stored_not_recomputed(self):
        plan_id = self.prepare_swap()
        issued = self.issue(freeze_schedule(self.archive, plan_id, ABA))
        report_id = issued[0].report_id
        payload = self.archive.connection.execute(
            'SELECT payload FROM schedule_reports WHERE report_id = ?', (report_id,),
        ).fetchone()[0]
        value = json.loads(payload)
        value['round_occupation'] = ['1/4', '3/4']
        self.archive.connection.execute(
            'UPDATE schedule_reports SET payload = ? WHERE report_id = ?',
            (json.dumps(value), report_id),
        )
        stored = read_schedule_report(self.archive, report_id)
        self.assertEqual(stored[0].round_occupation, (F(1, 4), F(3, 4)))
        self.assertEqual(stored[0].stage_occupations, issued[0].stage_occupations)

    def test_rollback_and_retry(self):
        plan_id = self.prepare_swap()
        old = self.issue(freeze_schedule(self.archive, plan_id, ABA))
        schedule_id = freeze_schedule(self.archive, plan_id, ABB)
        baseline = self.schedule_counts()
        stages = []

        def abort():
            stages.append(self.schedule_counts())
            raise InjectedCommitFailure('cancel before commit')

        with self.assertRaisesRegex(InjectedCommitFailure, 'cancel before commit'):
            issue_schedule_report(self.archive, schedule_id, before_commit=abort)
        self.assertEqual(stages, [(2, 2, 2)])
        self.assertEqual(self.schedule_counts(), baseline)
        self.assertEqual(read_schedule_report(self.archive, old[0].report_id), old)
        retried = issue_schedule_report(self.archive, schedule_id)
        self.assertEqual(read_schedule_report(self.archive, retried[0].report_id), retried)
        self.assertEqual(self.schedule_counts(), (2, 2, 2))

    def test_reopen_atomic(self):
        plan_id = self.prepare_swap()
        old = self.issue(freeze_schedule(self.archive, plan_id, ABA))
        schedule_id = freeze_schedule(self.archive, plan_id, ABB)
        counts = self.schedule_counts()
        staged_ids = []
        with HandoverArchive.open(self.archive_path) as observer:
            def abort():
                self.assertEqual(self.schedule_counts(), (2, 2, 2))
                self.assertEqual(self.schedule_counts(observer), counts)
                staged = self.archive.connection.execute(
                    'SELECT report_id FROM schedule_reports WHERE schedule_id = ?', (schedule_id,),
                ).fetchone()[0]
                staged_ids.append(staged)
                with self.assertRaises(KeyError):
                    read_schedule_report(observer, staged)
                raise InjectedCommitFailure('interrupt staged schedule issue')

            with self.assertRaises(InjectedCommitFailure):
                issue_schedule_report(self.archive, schedule_id, before_commit=abort)
        self.reopen_archive()
        self.assertEqual(self.schedule_counts(), counts)
        with self.assertRaises(KeyError):
            read_schedule_report(self.archive, staged_ids[0])
        self.assertEqual(read_schedule_report(self.archive, old[0].report_id), old)

    def test_init_idempotent_and_v1_isolation(self):
        plan_id = self.prepare_swap()
        issued = self.issue(freeze_schedule(self.archive, plan_id, ABA))
        v1 = issue_report(self.archive, plan_id)
        for _ in range(2):
            self.archive.initialize()
            self.assertEqual(self.schedule_counts(), (1, 1, 1))
            self.assertEqual(self.archive_counts(), (1, 1, 1))
            self.assertEqual(read_schedule_report(self.archive, issued[0].report_id), issued)
            self.assertEqual(read_report(self.archive, v1[0].report_id), v1)
        self.disconnect_source()
        self.reopen_archive()
        self.assertEqual(read_schedule_report(self.archive, issued[0].report_id), issued)
        self.assertEqual(read_report(self.archive, v1[0].report_id), v1)

    def test_report_validation(self):
        plan_id = self.prepare_swap()
        report, receipt = self.issue(freeze_schedule(self.archive, plan_id, ABA))
        bad_cases = (
            replace(report, stage_occupations=report.stage_occupations[:-1]),
            replace(report, round_occupation=(F(2, 3),)),
            replace(report, round_occupation=(F(1, 3), F(1, 3))),
            replace(report, stage_occupations=report.stage_occupations + ((F(1), F(0)),)),
            replace(report, stages=report.stages[:-1]),
            replace(report, stations=('A',)),
            replace(report, schedule_id='  '),
        )
        for value in bad_cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_schedule_report(value)

    def test_periodic_round_and_large_step_counts(self):
        report, _ = self.issue(freeze_schedule(self.archive, prepare_split_plan(self.source, self.archive), ZERO_SPLIT))
        self.assertEqual(report.round_occupation, (F(0), F(1, 3), F(2, 3)))
        # A periodic round still averages across the whole round.
        cycle = (
            RouteRule('ab', 'A', 'B', 1, 0),
            RouteRule('bc', 'B', 'C', 1, 0),
            RouteRule('ca', 'C', 'A', 1, 0),
        )
        revision_id = record_revision(self.source, ('A', 'B', 'C'), ('1/2', '1/2', 0), cycle)
        cycle_plan = freeze_plan(self.source, self.archive, revision_id)
        whole, _ = self.issue(freeze_schedule(self.archive, cycle_plan, (('loop', 1, 3),)))
        self.assertEqual(whole.stage_occupations, ((F(1, 3), F(1, 3), F(1, 3)),))
        split, _ = self.issue(freeze_schedule(self.archive, cycle_plan, (
            ('a', 1, 1), ('b', 1, 1), ('c', 1, 1),
        )))
        self.assertEqual(split.stage_occupations, (
            (F(1, 2), F(1, 2), F(0)), (F(0), F(1, 2), F(1, 2)), (F(1, 2), F(0), F(1, 2)),
        ))
        self.assertEqual(split.round_occupation, (F(1, 3), F(1, 3), F(1, 3)))
        # Long stages use exact fast powers rather than step-by-step drift.
        swap_plan = self.prepare_swap()
        long_stage, _ = self.issue(freeze_schedule(self.archive, swap_plan, (('observe', 1, 1000),)))
        self.assertEqual(long_stage.stage_occupations, ((F(1, 2), F(1, 2)),))
        self.assertEqual(long_stage.round_occupation, (F(1, 2), F(1, 2)))

    def test_draft_matches_issue(self):
        plan_id = self.prepare_swap()
        schedule_id = freeze_schedule(self.archive, plan_id, WEIGHTED)
        schedule = ScheduleStore(self.archive).load(schedule_id)
        draft = schedule_occupation(PlanStore(self.archive).load(plan_id), schedule)
        report, _ = self.issue(schedule_id)
        self.assertEqual(draft.stage_occupations, report.stage_occupations)
        self.assertEqual(draft.round_occupation, report.round_occupation)
        self.assertEqual(draft.stages, report.stages)

