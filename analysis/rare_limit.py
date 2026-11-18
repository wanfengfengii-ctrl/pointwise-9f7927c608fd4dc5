from fractions import Fraction
from itertools import product
from math import prod

from plan.snapshot import FrozenPlan

LeadingTerm = tuple[int, Fraction]


def _leading_edges(plan: FrozenPlan) -> list[dict[int, LeadingTerm]]:
    index = {station: position for position, station in enumerate(plan.stations)}
    edges: list[dict[int, LeadingTerm]] = [{} for _ in index]
    for route in plan.routes:
        if not route.base_probability or route.source == route.destination:
            continue
        source = index[route.source]
        target = index[route.destination]
        previous = edges[source].get(target)
        order = route.releases
        coefficient = route.base_probability
        if previous is None or order < previous[0]:
            edges[source][target] = (order, coefficient)
        elif order == previous[0]:
            edges[source][target] = (order, previous[1] + coefficient)
    return edges


def _leads_to_root(root: int, parents: dict[int, int]) -> bool:
    reached = {root}
    while len(reached) <= len(parents):
        newly_reached = {source for source, target in parents.items() if target in reached} - reached
        if not newly_reached:
            return False
        reached.update(newly_reached)
    return True


def _leading_root_weight(root: int, edges: list[dict[int, LeadingTerm]]) -> LeadingTerm:
    sources = tuple(source for source in range(len(edges)) if source != root)
    best_order = None
    coefficient = Fraction(0)
    for choices in product(*(edges[source].items() for source in sources)):
        parents = dict(zip(sources, (target for target, _ in choices), strict=True))
        if not _leads_to_root(root, parents):
            continue
        order = sum(term[0] for _, term in choices)
        if best_order is not None and order > best_order:
            continue
        contribution = prod((term[1] for _, term in choices), start=Fraction(1))
        if best_order is None or order < best_order:
            best_order = order
            coefficient = contribution
        else:
            coefficient += contribution
    if best_order is None:
        raise ValueError('fixed plan support has no spanning tree for a station')
    return best_order, coefficient


def rare_occupation_limit(plan: FrozenPlan) -> tuple[Fraction, ...]:
    """Take the exact zero-right limit of the positive-release stationary weights."""
    # All tree contributions are nonnegative, so only the leading term of each edge matters.
    edges = _leading_edges(plan)
    weights = tuple(_leading_root_weight(root, edges) for root in range(len(edges)))
    first_order = min(order for order, _ in weights)
    normalizer = sum(coefficient for order, coefficient in weights if order == first_order)
    return tuple(coefficient / normalizer if order == first_order else Fraction(0) for order, coefficient in weights)
