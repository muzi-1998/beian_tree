"""Hierarchical evidence-aware D1-D5 aggregation."""


def run_aggregation():
    """Run the frozen aggregation pipeline without importing heavy modules eagerly."""
    from .runner import run_aggregation as _run_aggregation

    return _run_aggregation()


__all__ = ["run_aggregation"]
