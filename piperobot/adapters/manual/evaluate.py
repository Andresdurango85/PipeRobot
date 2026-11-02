"""Convert operator-recorded attempts from CSV to evaluation results.

On real hardware the seed is an episode label (the attempt number), not a
reproducibility handle; the contract's uniqueness check still applies.

Usage:
    python -m piperobot.adapters.manual.evaluate --attempts attempts.csv \\
        --policy candidate --output out/results.json
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from piperobot.results import EpisodeResult, EvalResults, ResultsError, save_results

ALLOWED_COLUMNS = ("attempt", "success", "failure", "scene", "video_url")
SUCCESS_VALUES = {"true": True, "yes": True, "1": True, "false": False, "no": False, "0": False}


def load_attempts(path: Path, policy: str) -> EvalResults:
    episodes: list[EpisodeResult] = []
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            header_line = stream.readline()
            delimiter = ";" if ";" in header_line and "," not in header_line else ","
            stream.seek(0)
            reader = csv.reader(stream, delimiter=delimiter, strict=True)
            header = next(reader, [])
            unknown = set(header) - set(ALLOWED_COLUMNS)
            missing = {"attempt", "success"} - set(header)
            if unknown or missing or len(header) != len(set(header)):
                raise ResultsError(
                    f"{path}: invalid header: missing {sorted(missing)}, "
                    f"unknown {sorted(unknown)}; column names must be unique; "
                    f"allowed columns: {', '.join(ALLOWED_COLUMNS)}"
                )
            for cells in reader:
                # Excel saves trailing blank rows as ",,," (or ";;;").
                if not any(cell.strip() for cell in cells):
                    continue
                location = f"{path}: line {reader.line_num}"
                if len(cells) != len(header):
                    raise ResultsError(
                        f"{location}: expected {len(header)} cells, got {len(cells)}"
                    )
                row = dict(zip(header, cells, strict=True))
                try:
                    attempt = int(row["attempt"])
                except ValueError as exc:
                    raise ResultsError(
                        f"{location}: attempt must be a positive integer, got {row['attempt']!r}"
                    ) from exc
                if attempt <= 0:
                    raise ResultsError(f"{location}: attempt must be positive, got {attempt}")
                location += f", attempt {attempt}"
                spelling = row["success"].strip().lower()
                if spelling not in SUCCESS_VALUES:
                    raise ResultsError(
                        f"{location}: invalid success value {row['success']!r} "
                        "(use yes/no, true/false or 1/0)"
                    )
                success = SUCCESS_VALUES[spelling]
                failure = row.get("failure", "").strip() or None
                if success and failure:
                    raise ResultsError(f"{location}: successful attempt cannot have a failure note")
                episodes.append(
                    EpisodeResult(
                        seed=attempt,
                        success=success,
                        failure=failure,
                        scene=row.get("scene", "").strip() or None,
                        video_url=row.get("video_url", "").strip() or None,
                    )
                )
    except csv.Error as exc:
        raise ResultsError(f"{path}: line {reader.line_num}: cannot read attempts: {exc}") from exc
    except UnicodeError as exc:
        raise ResultsError(
            f"{path}: cannot read attempts: not UTF-8 (from Excel, save as 'CSV UTF-8'): {exc}"
        ) from exc
    except OSError as exc:
        raise ResultsError(f"{path}: cannot read attempts: {exc}") from exc
    if not episodes:
        raise ResultsError(f"{path}: no attempts recorded")
    counts = Counter(episode.seed for episode in episodes)
    missing_attempts = sorted(set(range(1, max(counts) + 1)) - counts.keys())
    duplicates = sorted(attempt for attempt, count in counts.items() if count > 1)
    if missing_attempts or duplicates:
        raise ResultsError(
            f"{path}: attempts must be exactly 1..N; "
            f"missing attempts: {missing_attempts}; duplicated attempts: {duplicates}"
        )
    return EvalResults(policy, "manual", tuple(sorted(episodes, key=lambda episode: episode.seed)))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--attempts", type=Path, required=True, help="Operator-recorded CSV file")
    parser.add_argument("--policy", required=True, help="Evaluated policy name")
    parser.add_argument("--output", type=Path, required=True, help="Where to write results JSON")
    args = parser.parse_args(argv)
    try:
        results = load_attempts(args.attempts, args.policy)
    except ResultsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    save_results(results, args.output)
    print(f"{results.policy}: {results.successes}/{results.trials} attempts succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
