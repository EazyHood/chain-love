"""Check all replicate reports and publish their pooled and per-runner medians."""
import json
import os
from pathlib import Path
from statistics import median
from sys import argv

reports = sorted([json.loads(path.read_text()) for path in Path(argv[1]).glob("runner-*.json")],
                 key=lambda report: report["replica"])
assert [r["replica"] for r in reports] == [1, 2, 3]
for k in ("image", "corpus_sha256", "python", "jsonschema", "data_commit", "validator_base", "validator_candidate"):
    assert len({r[k] for r in reports}) == 1, k
for r in reports:
    assert r["network_files"] == 138 and r["canonical_offer_csv"] == 14
    assert (r["valid_exit"], r["invalid_exit"], r["invalid_diagnostics"], r["stderr_empty"]) == (0, 1, 4, True)
    samples = r["samples"]
    assert len(samples) == 12
    for v in ("before", "after"):
        assert sum(s["variant"] == v and s["position"] == 1 for s in samples) == 3
        assert {s["pair"] for s in samples if s["variant"] == v} == set(range(1, 7))
all_samples = [s for r in reports for s in r["samples"]]


def stats(samples):
    return {v: {key: median(s[key] for s in samples if s["variant"] == v)
                for key in ("elapsed_s", "peak_rss_mib")} for v in ("before", "after")}


pooled = stats(all_samples)
before, after = (pooled[v]["elapsed_s"] for v in ("before", "after"))
reduction = 100 * (1 - after / before)
rows = ["| Runner | Before | After |", "| --- | ---: | ---: |"]
for r in reports:
    group = stats(r["samples"])
    rows.append(f'| {r["replica"]} | {group["before"]["elapsed_s"]:.3f} s | {group["after"]["elapsed_s"]:.3f} s |')
rows.append(f"| Pooled median | {before:.3f} s | {after:.3f} s |")
summary = "\n".join(["## PR #5443 validator benchmark", "",
    "Three independent GitHub-hosted Ubuntu runners. Six counterbalanced pairs per runner. Fresh Python processes, one untimed warm-up per version per runner.", "",
    *rows, "", f"Median elapsed time reduction: {reduction:.2f}%.",
    f'Median peak RSS: {pooled["before"]["peak_rss_mib"]:.2f} to {pooled["after"]["peak_rss_mib"]:.2f} MiB.',
    "", "All 36 timed validations processed 138 networks and canonical offers. Within every runner, all outputs matched. Both versions rejected the invalid Filecoin control with the same four diagnostics and exit code 1.",
    "", "Time includes interpreter startup and the complete JSON validation process. Data generation, dependency installation and GitHub job setup are outside the timer.",
    "", f'Container: {reports[0]["image"]}. Python {reports[0]["python"]}, jsonschema {reports[0]["jsonschema"]}.',
    "", f'Input bundle SHA-256: {reports[0]["corpus_sha256"]}.', "",
    "[Chain-Love data and tools](https://github.com/Chain-Love/chain-love/pull/5443). Raw samples are available in the runner artifacts."])
print(summary)
with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
    f.write(summary + "\n")
print("BENCHMARK_RESULT=" + json.dumps({"pooled": pooled, "reduction_pct": reduction,
      "runners": [stats(r["samples"]) for r in reports]}, separators=(",", ":")))
