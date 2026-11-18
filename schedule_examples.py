from fractions import Fraction as F

from archive.catalog import HandoverArchive
from plan.audit import audit_plan
from plan.freeze import freeze_plan
from publication.issue import issue_report
from routing.intake import record_revision
from routing.revision_store import RevisionStore
from routing.routes import RouteRule


SWAP_ROUTES = (
    RouteRule("a-to-b", "A", "B", 1, 1),
    RouteRule("b-to-a", "B", "A", 1, 1),
)
SPLIT_ROUTES = (
    RouteRule("a-to-b", "A", "B", "1/4", 0),
    RouteRule("a-to-c", "A", "C", "1/2", 0),
    RouteRule("b-to-a", "B", "A", "1/2", 1),
    RouteRule("c-to-a", "C", "A", "1/2", 1),
)

ABA = (("transfer", 1, 1), ("return", 1, 1), ("observe", 0, 1))
ABB = (("transfer", 1, 1), ("observe", 0, 1), ("return", 1, 1))
WEIGHTED = (("transfer", 1, 1), ("return", 1, 1), ("observe", 0, 2))
SINGLE_SWAP = (("transfer", 1, 1),)
DOUBLE_SWAP = (("transfer", 1, 2),)
ZERO_SPLIT = (("observe", 0, 1), ("check", 0, 2))


def prepare_swap_plan(source, archive):
    revision_id = record_revision(source, ("A", "B"), (1, 0), SWAP_ROUTES)
    return freeze_plan(source, archive, revision_id)


def prepare_split_plan(source, archive):
    revision_id = record_revision(source, ("A", "B", "C"), (1, 0, 0), SPLIT_ROUTES)
    return freeze_plan(source, archive, revision_id)


def main():
    with RevisionStore(":memory:") as source, HandoverArchive.open(":memory:") as archive:
        swap_plan = prepare_swap_plan(source, archive)
        for ratio in (0, 1):
            audit = audit_plan(archive, swap_plan, ratio)
            routes = tuple(row.probability for row in audit.routes)
            expected = (F(ratio), F(ratio))
            if routes != expected or audit.remaining != (1 - ratio, 1 - ratio):
                raise AssertionError(f"unexpected V1 route audit at ratio {ratio}: {audit!r}")
            print(f"ratio={ratio} routes={tuple(map(str, routes))} remaining={tuple(map(str, audit.remaining))}")
        split_plan = prepare_split_plan(source, archive)
        split, _ = issue_report(archive, split_plan)
        if split.stations != ("A", "B", "C") or split.zero != (F(0), F(1, 3), F(2, 3)):
            raise AssertionError(f"unexpected V1 zero-ratio split: {split!r}")
        print(f"zero-ratio split {split.stations}: {tuple(map(str, split.zero))}")


if __name__ == "__main__":
    main()
