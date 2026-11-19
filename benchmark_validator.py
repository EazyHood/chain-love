"""Benchmark the complete validator process on one GitHub-hosted Linux runner."""
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path
from statistics import median
from time import perf_counter

DATA = Path("/data")
OUT = Path("/results")


def invoke(label, directory, expected_status):
    # wait4 returns this child's high-water mark. Linux reports it in KiB.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        start = perf_counter()
        with subprocess.Popen([sys.executable, "-B", "-X", "utf8", str(DATA / (label + ".py"))],
                              cwd=directory, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr) as child:
            _, status, usage = os.wait4(child.pid, 0)
            elapsed = perf_counter() - start
            child.returncode = os.waitstatus_to_exitcode(status)
        stdout.seek(0)
        stderr.seek(0)
        output, errors = stdout.read(), stderr.read()
    if child.returncode != expected_status or errors:
        raise RuntimeError((label, child.returncode, output[-1200:], errors[-1200:]))
    return output, {"variant": label, "elapsed_s": elapsed, "peak_rss_mib": usage.ru_maxrss / 1024}


def negative_control():
    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory)
        for name in ("schema.json", "references", "meta"):
            (scratch / name).symlink_to(DATA / name)
        (scratch / "json").mkdir()
        document = json.loads((DATA / "json/filecoin.json").read_bytes())
        document["schemaVersion"] = 7
        for row in document["analytics"][:2]:
            row["slug"] = 3.75
        (scratch / "json/filecoin.json").write_text(json.dumps(document))
        before, _ = invoke("before", scratch, 1)
        after, _ = invoke("after", scratch, 1)
        if before != after or before.count(b"Error message") != 4:
            raise RuntimeError("Invalid Filecoin did not return the same four diagnostics.")
        return hashlib.sha256(before).hexdigest()


def main():
    replica = int(os.environ["REPLICA"])
    files = sorted((DATA / "json").glob("*.json"))
    assert len(files) == 138 and len(list((DATA / "references/offers").glob("*.csv"))) == 14
    expected_lines = {("Validating " + p.name + "...").encode() for p in files}
    warm_order = ("before", "after") if replica % 2 else ("after", "before")
    reference, _ = invoke(warm_order[0], DATA, 0)
    assert set(reference.splitlines()) == expected_lines and len(reference.splitlines()) == 138
    assert invoke(warm_order[1], DATA, 0)[0] == reference
    samples = []
    for pair in range(1, 7):
        order = ("before", "after") if (pair + replica) % 2 == 0 else ("after", "before")
        for position, variant in enumerate(order, 1):
            output, sample = invoke(variant, DATA, 0)
            assert output == reference
            sample.update(pair=pair, position=position)
            print(json.dumps(sample), flush=True)
            samples.append(sample)
    result = {"replica": replica, "python": platform.python_version(), "jsonschema": version("jsonschema"),
              "image": os.environ["IMAGE"], "corpus_sha256": os.environ["CORPUS_SHA"],
              "validator_base": os.environ["BASE"], "validator_candidate": os.environ["CANDIDATE"],
              "data_commit": os.environ["DATA_COMMIT"], "network_files": len(files), "canonical_offer_csv": 14,
              "valid_stdout_sha256": hashlib.sha256(reference).hexdigest(), "invalid_stdout_sha256": negative_control(),
              "valid_exit": 0, "invalid_exit": 1, "invalid_diagnostics": 4, "stderr_empty": True, "samples": samples}
    output = OUT / f"runner-{replica}.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    for variant in ("before", "after"):
        group = [s for s in samples if s["variant"] == variant]
        print(variant, "median wall seconds", median(s["elapsed_s"] for s in group))


if __name__ == "__main__":
    main()
