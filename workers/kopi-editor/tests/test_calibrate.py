"""Unit tests for the calibration-log summariser."""
import json

import calibrate


def _rec(input_wc, output_wc, accepted, fat):
    return {
        "ts": 0.0,
        "index": 0,
        "input_wc": input_wc,
        "output_wc": output_wc,
        "compression_ratio": round((input_wc - output_wc) / input_wc, 4),
        "accepted": accepted,
        "reason": "ok" if accepted else "meaning drift",
        "fat_index": fat,
        "routing_reason": "fat-index 0.50, rank 1/3",
    }


def test_load_records_roundtrip(tmp_path):
    path = tmp_path / "calibration.jsonl"
    recs = [_rec(100, 75, True, 0.8), _rec(100, 95, False, 0.2)]
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    loaded = calibrate.load_records(path)
    assert len(loaded) == 2
    assert loaded[0]["input_wc"] == 100


def test_load_records_skips_bad_lines(tmp_path):
    path = tmp_path / "calibration.jsonl"
    path.write_text('{"ok": 1}\nnot-json\n\n{"ok": 2}\n', encoding="utf-8")
    assert len(calibrate.load_records(path)) == 2


def test_summarise_reports_rates_and_buckets():
    records = [
        _rec(100, 70, True, 0.9),
        _rec(100, 80, True, 0.8),
        _rec(100, 98, False, 0.1),
    ]
    out = calibrate.summarise(records)
    assert "3 paragraph attempts" in out
    assert "2 accepted" in out
    assert "Rejection rate by fat-index bucket" in out
    assert "Compression distribution" in out


def test_summarise_empty():
    assert "No calibration records" in calibrate.summarise([])


def test_helpers():
    assert calibrate._median([1, 2, 3]) == 2
    assert calibrate._median([1, 2, 3, 4]) == 2.5
    assert calibrate._mean([2, 4]) == 3
    assert calibrate._mean([]) == 0.0
