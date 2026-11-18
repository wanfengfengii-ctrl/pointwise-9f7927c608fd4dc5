from collections.abc import Sequence
from fractions import Fraction

from analysis.closed_classes import decompose_closed_classes
from analysis.linear_system import solve_fraction_system, stationary_distribution

Matrix = tuple[tuple[Fraction, ...], ...]


def validate_square(matrix: Sequence[Sequence[Fraction]]) -> None:
    size = len(matrix)
    if any(len(row) != size for row in matrix):
        raise ValueError('transition matrix must be square')


def matrix_multiply(left: Matrix, right: Matrix) -> Matrix:
    size = len(left)
    if len(right) != size:
        raise ValueError('transition matrices must have the same size')
    validate_square(left)
    validate_square(right)
    return tuple(
        tuple(
            sum((left[row][middle] * right[middle][column] for middle in range(size)), Fraction(0))
            for column in range(size)
        )
        for row in range(size)
    )


def multiply_vector(vector: Sequence[Fraction], matrix: Matrix) -> tuple[Fraction, ...]:
    size = len(matrix)
    if len(vector) != size:
        raise ValueError('vector and matrix dimensions do not agree')
    validate_square(matrix)
    return tuple(
        sum((vector[middle] * matrix[middle][column] for middle in range(size)), Fraction(0))
        for column in range(size)
    )


def identity_matrix(size: int) -> Matrix:
    if type(size) is not int or size < 0:
        raise ValueError('matrix size must be a nonnegative integer')
    return tuple(
        tuple(Fraction(int(row == column)) for column in range(size))
        for row in range(size)
    )


def matrix_add(left: Matrix, right: Matrix) -> Matrix:
    validate_square(left)
    validate_square(right)
    if len(left) != len(right):
        raise ValueError('transition matrices must have the same size')
    return tuple(
        tuple(left[row][column] + right[row][column] for column in range(len(left)))
        for row in range(len(left))
    )


def matrix_power(matrix: Matrix, exponent: int) -> Matrix:
    """Raise a square matrix to a nonnegative integer power by exact squaring."""
    validate_square(matrix)
    if type(exponent) is not int or exponent < 0:
        raise ValueError('matrix exponent must be a nonnegative integer')
    result = identity_matrix(len(matrix))
    base = tuple(tuple(Fraction(value) for value in row) for row in matrix)
    while exponent:
        if exponent & 1:
            result = matrix_multiply(result, base)
        exponent >>= 1
        if exponent:
            base = matrix_multiply(base, base)
    return result


def matrix_power_sum(matrix: Matrix, count: int) -> Matrix:
    """Return matrix**0 + matrix**1 + ... + matrix**(count - 1) exactly."""
    validate_square(matrix)
    if type(count) is not int or count < 0:
        raise ValueError('power-sum length must be a nonnegative integer')
    size = len(matrix)
    if not count:
        return tuple(tuple(Fraction(0) for _ in range(size)) for _ in range(size))
    if count == 1:
        return identity_matrix(size)
    half = count // 2
    halves = matrix_power_sum(matrix, half)
    doubled = matrix_multiply(matrix_add(identity_matrix(size), matrix_power(matrix, half)), halves)
    if count % 2 == 0:
        return doubled
    return matrix_add(doubled, matrix_power(matrix, count - 1))


def long_run_distribution(
    matrix: Matrix,
    initial: Sequence[Fraction],
) -> tuple[Fraction, ...]:
    """Cesaro limit of the state distribution started from ``initial``.

    The limit exists for every finite chain: mass is apportioned to each closed
    class by its absorption probability from the transient states, and the
    unique stationary distribution of that class (also valid for periodic
    classes) spreads it inside the class.
    """
    size = len(matrix)
    validate_square(matrix)
    if len(initial) != size:
        raise ValueError('initial distribution and transition matrix dimensions do not agree')
    start = tuple(Fraction(value) for value in initial)
    partition = decompose_closed_classes(matrix)
    transient = partition.transient
    occupation = [Fraction(0) for _ in range(size)]
    if transient:
        absorption_system = [
            [Fraction(int(source == target)) - matrix[source][target] for target in transient]
            for source in transient
        ]
        direct_entries = [
            [sum((matrix[source][target] for target in closed), Fraction(0)) for source in transient]
            for closed in partition.classes
        ]
    else:
        absorption_system = []
        direct_entries = [[] for _ in partition.classes]
    for closed, direct_entry in zip(partition.classes, direct_entries, strict=True):
        hitting = solve_fraction_system(absorption_system, direct_entry) if transient else ()
        weight = sum((start[station] for station in closed), Fraction(0))
        weight += sum((start[station] * probability for station, probability in zip(transient, hitting, strict=True)), Fraction(0))
        class_matrix = tuple(tuple(matrix[source][target] for target in closed) for source in closed)
        within = stationary_distribution(class_matrix)
        for station, probability in zip(closed, within, strict=True):
            occupation[station] = weight * probability
    return tuple(occupation)

