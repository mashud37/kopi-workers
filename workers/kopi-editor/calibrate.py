"""Summarise the Step 10 calibration log so the user can tune routing.

The pipeline appends one JSONL record per LLM-edited paragraph to the
calibration log (default ``~/.kopi/calibration.jsonl``, overridable with
``KOPI_CALIBRATION_LOG``). Each record holds the input/output word counts, the
achieved compression ratio, whether the cosine/citation/numeric guard accepted
the edit, and the paragraph's fat-index.

Run:  python calibrate.py [path]

It prints mean/median compression, the compression distribution, and the
rejection rate bucketed by fat-index — the inputs you need to hand-tune
``signals.EXPECTED_COMPRESSION`` and ``signals.FAT_WEIGHTS``. It never auto-tunes.
"""
import json
import os
import sys
from pathlib import Path


def _log_path(argv) -> Path:
    if len(argv) > 1:
        return Path(argv[1])
    override = os.environ.get("KOPI_CALIBRATION_LOG")
    return Path(override) if override else Path.home() / ".kopi" / "calibration.jsonl"


def load_records(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _median(xs):
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _histogram(ratios, width=40):
    """Text histogram of compression ratios in 0.05-wide bins from 0 to 0.45+."""
    edges = [i * 0.05 for i in range(10)]  # 0.00 .. 0.45
    counts = [0] * (len(edges) + 1)
    for r in ratios:
        placed = False
        for i, e in enumerate(edges):
            if r < e + 0.05:
                counts[i] += 1
                placed = True
                break
        if not placed:
            counts[-1] += 1
    peak = max(counts) or 1
    lines = []
    for i, c in enumerate(counts):
        lo = i * 0.05
        label = f">={lo:.2f}" if i == len(counts) - 1 else f"{lo:.2f}-{lo + 0.05:.2f}"
        bar = "#" * int(width * c / peak)
        lines.append(f"  {label:>11} | {bar} {c}")
    return "\n".join(lines)


def summarise(records: list[dict]) -> str:
    if not records:
        return "No calibration records found."

    accepted = [r for r in records if r.get("accepted")]
    ratios_all = [r.get("compression_ratio", 0.0) for r in records]
    ratios_acc = [r.get("compression_ratio", 0.0) for r in accepted]
    rejection_rate = 1 - len(accepted) / len(records)

    out = []
    out.append(f"Calibration: {len(records)} paragraph attempts, "
               f"{len(accepted)} accepted ({100 * len(accepted) / len(records):.0f}%)")
    out.append("")
    out.append("Compression ratio (accepted edits):")
    out.append(f"  mean   : {_mean(ratios_acc):.3f}")
    out.append(f"  median : {_median(ratios_acc):.3f}")
    out.append(f"  -> compare against signals.EXPECTED_COMPRESSION (projection input)")
    out.append("")
    out.append("Compression distribution (all attempts):")
    out.append(_histogram(ratios_all))
    out.append("")
    out.append(f"Overall rejection rate: {rejection_rate:.1%}")

    # Rejection rate bucketed by fat-index (only records that carry one).
    fat_records = [r for r in records if isinstance(r.get("fat_index"), (int, float))]
    if fat_records:
        out.append("")
        out.append("Rejection rate by fat-index bucket:")
        buckets = [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)]
        for lo, hi in buckets:
            in_bucket = [r for r in fat_records if lo <= r["fat_index"] < hi]
            if not in_bucket:
                continue
            rej = sum(1 for r in in_bucket if not r.get("accepted")) / len(in_bucket)
            mean_c = _mean([r.get("compression_ratio", 0.0) for r in in_bucket if r.get("accepted")])
            out.append(f"  [{lo:.2f}, {hi if hi <= 1 else 1.0:.2f}): "
                       f"n={len(in_bucket):>3}  reject={rej:.0%}  mean_compression(acc)={mean_c:.3f}")
    else:
        out.append("")
        out.append("(No fat-index values logged — likely cloud-only runs.)")

    return "\n".join(out)


def main():
    path = _log_path(sys.argv)
    if not path.exists():
        print(f"No calibration log at {path}", file=sys.stderr)
        print("Run the pipeline with the LLM step first, or pass a log path.", file=sys.stderr)
        sys.exit(1)
    print(summarise(load_records(path)))


if __name__ == "__main__":
    main()
