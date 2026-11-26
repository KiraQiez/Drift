"""Time an installed Drift snapshot against an isolated small fixture."""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

SAMPLES = 7
TARGET_SECONDS = 2.0


def main() -> None:
    interpreter = Path(sys.executable)
    executable = interpreter.with_name("drift.exe" if os.name == "nt" else "drift")
    environment = os.environ | {
        "PATH": str(interpreter.parent),
        "DRIFT_TIMING_FIXTURE": "fixture-value",
    }
    with TemporaryDirectory(prefix="drift-capture-timing-") as directory:
        root = Path(directory)
        command = [str(executable), "--project", str(root)]
        subprocess.run(
            [*command, "init", "--json"],
            check=True,
            capture_output=True,
            cwd=root,
            env=environment,
            timeout=15,
        )
        (root / "drift.toml").write_text(
            "schema_version = 1\n[collectors]\ndocker=false\ngit=false\n"
            '[environment]\nfiles=["fixture.env"]\nactive_allowlist=["DRIFT_TIMING_FIXTURE"]\n',
            encoding="utf-8",
        )
        (root / "fixture.env").write_text(
            "FIXTURE_DECLARATION=fixture\n", encoding="utf-8"
        )
        (root / "requirements.txt").write_text("fixture==1\n", encoding="utf-8")
        (root / "package.json").write_text(
            '{"name":"fixture","version":"1.0.0"}\n', encoding="utf-8"
        )
        elapsed = []
        for _ in range(SAMPLES):
            start = perf_counter()
            completed = subprocess.run(
                [*command, "snapshot", "--json"],
                check=True,
                capture_output=True,
                cwd=root,
                env=environment,
                timeout=15,
            )
            elapsed.append(perf_counter() - start)
            snapshot = json.loads(completed.stdout)["result"]["snapshot"]
            statuses = snapshot["collector_statuses"]
            if any(
                statuses[name] != "ok"
                for name in ("system", "runtime", "environment", "dependency")
            ):
                raise RuntimeError(
                    "Timing fixture did not capture all expected observations."
                )

    midpoint = median(elapsed)
    print(
        json.dumps(
            {
                "fixture": "drift_capture",
                "platform": platform.system(),
                "architecture": platform.machine(),
                "python": platform.python_version(),
                "samples": SAMPLES,
                "median_s": round(midpoint, 3),
                "max_s": round(max(elapsed), 3),
                "target_s": TARGET_SECONDS,
                "within_target": midpoint < TARGET_SECONDS,
            }
        )
    )


if __name__ == "__main__":
    main()
