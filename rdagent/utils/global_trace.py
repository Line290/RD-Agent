"""Global trace library for cross-batch factor accumulation.

Stores successful (decision=True) experiments across multiple
factor_from_report.py runs. Can be loaded by factor.py for
trace-driven evolution.
"""

from pathlib import Path

from rdagent.core.proposal import Trace
from rdagent.core.serialization import dumps, loads

# Each entry is (experiment, feedback) where feedback.decision == True
TraceEntry = tuple[object, object]


def load_global_trace(path: str) -> list[TraceEntry]:
    """Load global trace entries from file.

    Returns a list of (experiment, feedback) tuples.
    Returns empty list if file does not exist.
    """
    p = Path(path)
    if not p.exists():
        return []
    with open(p, "rb") as f:
        return loads(f.read())


def save_global_trace(path: str, entries: list[TraceEntry]) -> None:
    """Save global trace entries to file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        f.write(dumps(entries))


def seed_trace_from_global(trace: Trace, path: str) -> int:
    """Populate a Trace object's hist with global trace entries.

    Inserts entries at the beginning of trace.hist so that
    based_experiments and hypothesis generation can see historical
    successes. Returns the number of entries loaded.
    """
    entries = load_global_trace(path)
    if not entries:
        return 0

    # Prepend global entries to the existing trace
    for exp, fb in entries:
        idx = len(trace.hist)
        trace.hist.append((exp, fb))
        trace.dag_parent.append(() if idx == 0 else (idx - 1,))
        trace.idx2loop_id[idx] = idx

    return len(entries)


def append_to_global_trace(path: str, exp, feedback) -> None:
    """Append a single (exp, feedback) entry to the global trace.

    Only call this when feedback.decision is True (successful experiment).
    """
    entries = load_global_trace(path)
    entries.append((exp, feedback))
    save_global_trace(path, entries)
