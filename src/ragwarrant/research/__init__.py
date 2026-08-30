"""Research-only governance benchmarks.

This namespace is intentionally isolated from the public promotion decision path.
"""

from .benchmark import run_benchmark
from .simulator import load_config

__all__ = ["load_config", "run_benchmark"]
