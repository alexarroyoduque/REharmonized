"""MP2K timing, automatic tempo selection and gap suggestions."""
from __future__ import annotations



PPQN = 24            # ticks per beat


MAX_WAIT_TICKS = 96  # ticks represented by the 0xB0 hold/wait opcode


DEFAULT_SUGGEST_GAPS = (-0.3, -0.6, -0.9, -1.2, -1.5, -1.8, -2.0)


def pick_tempo_and_holds(
    duration_s: float, tempo_override: int | None
) -> tuple[int, int, float]:
    """
    Choose a BB tempo byte and a count of 0xB0 hold bytes so the song holds
    its single tied note for approximately `duration_s` seconds before
    looping.

    seconds_per_tick   = 60 / (2 * tempo * PPQN) == 1.25 / tempo
    seconds_per_hold   = MAX_WAIT_TICKS * seconds_per_tick == 120 / tempo
    (BPM = 2 * tempo, 24 ticks/beat; see module docstring caveat. A previous
    version of this script assumed 48 ticks/beat, doubling every hold's real
    duration - the sample would finish, then wait through a second full
    silent copy of its own length before the loop pointer ever fired.)
    """
    if tempo_override is not None:
        tempo = tempo_override
        holds = max(1, round(duration_s * tempo / 120.0))
        return tempo, holds, holds * 120.0 / tempo

    best: tuple[float, int, int, float] | None = None
    for tempo in range(1, 256):
        holds = max(1, round(duration_s * tempo / 120.0))
        actual = holds * 120.0 / tempo
        error = abs(actual - duration_s)
        if best is None or error < best[0]:
            best = (error, tempo, holds, actual)

    assert best is not None
    _, tempo, holds, actual = best
    return tempo, holds, actual


def suggest_tempos(
    duration_s: float, target_gaps: list[float]
) -> list[tuple[float, int, int, float, float]]:
    """
    For each requested target gap (seconds), find the (tempo, holds)
    combination whose resulting gap (actual - duration_s) is closest to it.
    Returns one suggestion per target gap, in the same order.
    """
    results: list[tuple[float, int, int, float, float]] = []
    for target in target_gaps:
        best: tuple[float, int, int, float, float] | None = None
        for tempo in range(1, 256):
            holds = max(1, round(duration_s * tempo / 120.0))
            actual = holds * 120.0 / tempo
            gap = actual - duration_s
            error = abs(gap - target)
            if best is None or error < best[0]:
                best = (error, tempo, holds, actual, gap)
        assert best is not None
        _, tempo, holds, actual, gap = best
        results.append((target, tempo, holds, actual, gap))
    return results
