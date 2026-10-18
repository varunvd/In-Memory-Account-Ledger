"""Replay the six-day event stream and print the per-day report.

Usage:
    python3 replay.py
"""

from ledger.report import render
from ledger.scenario import WINDOW_DAYS, run_scenario


def main() -> None:
    ledger = run_scenario()
    print(render(ledger, WINDOW_DAYS))


if __name__ == "__main__":
    main()
