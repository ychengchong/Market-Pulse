"""Offline, versioned development evaluation for the extractive baseline."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.environment import text_digest, verify_environment
from src.summarizer import create_summary, normalise_text

ROOT = Path(__file__).resolve().parents[1]
FALLBACKS = ("No suitable", "The filing contained no readable text.")


def load_suite(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not manifest.get("cases"):
        raise ValueError("Unsupported or empty evaluation suite")
    seen = set()
    result = []
    for case in manifest["cases"]:
        if case["id"] in seen or case["split"] != "development":
            raise ValueError("Duplicate ID or unexpected split")
        seen.add(case["id"])
        fixture = (path.parent / case["fixture"]).resolve()
        if not fixture.is_relative_to(path.parent.resolve() / "fixtures"):
            raise ValueError("Fixture path outside suite")
        text = fixture.read_text(encoding="utf-8")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != case["input_sha256"]:
            raise ValueError(f"Fixture hash mismatch: {case['id']}")
        reference = case["reference"]
        for evidence in reference["required_evidence"]:
            if normalise_text(evidence) not in normalise_text(text):
                raise ValueError(f"Reference evidence absent from input: {case['id']}")
        result.append((case, text))
    return manifest, result


def score_prediction(prediction, reference):
    summary = normalise_text(prediction["summary"])
    checks = dict(
        event_type_correct=prediction["event_type"] == reference["event_type"],
        fallback_correct=summary.startswith(FALLBACKS) == reference["expect_fallback"],
        required_evidence_present=all(normalise_text(e) in summary for e in reference["required_evidence"]),
        forbidden_evidence_absent=all(normalise_text(e) not in summary for e in reference["forbidden_evidence"])
    )
    return dict(checks=checks, passed=all(checks.values()))


def evaluate(suite_path, predictor=create_summary):
    manifest, cases = load_suite(suite_path)
    results = []
    for case, text in cases:
        row = dict(id=case["id"], ticker=case["ticker"], form=case["form"], kind=case["kind"],
                   input_sha256=case["input_sha256"])
        try:
            prediction = predictor(text, form=case["form"])
            row.update(prediction=prediction, **score_prediction(prediction, case["reference"]))
        except Exception as error:
            # An evaluation must retain errors in its denominator.
            row.update(passed=False, error=f"{type(error).__name__}: {error}")
        results.append(row)
    slices = {}
    for field in ("form", "kind", "ticker"):
        slices[field] = {}
        for value in sorted({r[field] for r in results}):
            rows = [r for r in results if r[field] == value]
            slices[field][value] = dict(total=len(rows), passed=sum(r["passed"] for r in rows))
    return dict(suite_id=manifest["suite_id"], review=manifest["review"], scope=manifest["scope"],
                total=len(results), passed=sum(r["passed"] for r in results),
                errors=sum("error" in r for r in results),
                fallback_count=sum(r.get("prediction", {}).get("summary", "").startswith(FALLBACKS) for r in results),
                check_failures=dict(Counter(k for r in results for k,v in r.get("checks", {}).items() if not v)),
                slices=slices, results=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path, help="Compare against an existing baseline without overwriting it")
    args = parser.parse_args()
    if bool(args.output) == bool(args.verify):
        parser.error("Choose exactly one of --output or --verify")
    environment = verify_environment(ROOT)
    report = evaluate(ROOT / "evals/cases.json")
    code = {name: text_digest(ROOT / name) for name in ("src/summarizer.py", "evals/run.py", "scripts/environment.py")}
    report.update(schema_version=1, generated_at=datetime.now(timezone.utc).isoformat(),
                  source_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  code_sha256=code, suite_sha256=text_digest(ROOT / "evals/cases.json"), environment=environment)
    identity = dict(code_sha256=code, suite_sha256=report["suite_sha256"],
                    requirements_sha256=environment["requirements_sha256"])
    report["run_id"] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    if args.verify:
        previous = json.loads(args.verify.read_text(encoding="utf-8"))
        fields = ("run_id", "results", "total", "passed", "errors", "fallback_count", "slices", "check_failures")
        differences = [key for key in fields if previous.get(key) != report[key]]
        if differences:
            raise SystemExit("Baseline mismatch: " + ", ".join(differences))
        print("Baseline reproduced: inputs, code, lock, predictions and scores match.")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise SystemExit("Output exists; choose a new filename to preserve baseline history")
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"Cases: {report['total']}; passed: {report['passed']}; errors: {report['errors']}; fallbacks: {report['fallback_count']}")
    # Missing thresholds cannot turn scores into a release-quality claim.
    return 0 if report["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
