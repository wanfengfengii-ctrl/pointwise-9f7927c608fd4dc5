from archive.catalog import HandoverArchive
from archive.schedule_encoding import decode_schedule_payload, encode_schedule_payload
from archive.transactions import write_transaction
from plan.schedule import FrozenSchedule, validate_schedule
from routing.stations import validate_identity


class ScheduleStore:
    def __init__(self, archive: HandoverArchive):
        self.connection = archive.connection

    def save(self, schedule: FrozenSchedule) -> None:
        schedule = validate_schedule(schedule)
        with write_transaction(self.connection):
            self.connection.execute(
                'INSERT INTO schedules (schedule_id, plan_id, payload) VALUES (?, ?, ?)',
                (schedule.schedule_id, schedule.plan_id, encode_schedule_payload(schedule)),
            )

    def load(self, schedule_id: str) -> FrozenSchedule:
        validate_identity(schedule_id, 'schedule identity')
        row = self.connection.execute(
            'SELECT plan_id, payload FROM schedules WHERE schedule_id = ?', (schedule_id,),
        ).fetchone()
        if row is None:
            raise KeyError(schedule_id)
        plan_id, payload = row
        schedule = decode_schedule_payload(schedule_id, payload)
        if schedule.plan_id != plan_id:
            raise ValueError(f'archived schedule payload does not match its index for {schedule_id!r}')
        return schedule
