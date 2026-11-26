"""Install a distribution into isolated tool directories and run the console contract."""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("installer", choices=("uv", "pipx"))
    args = parser.parse_args()

    with TemporaryDirectory(prefix="drift install ") as temporary:
        root = Path(temporary)
        bin_dir = root / "bin"
        env = os.environ.copy()
        if args.installer == "uv":
            (artifact,) = args.directory.glob("*.whl")
            env.update(UV_TOOL_DIR=str(root / "tools"), UV_TOOL_BIN_DIR=str(bin_dir))
            command = ["uv", "tool", "install"]
        else:
            (artifact,) = args.directory.glob("*.tar.gz")
            env.update(
                PIPX_HOME=str(root / "tools"),
                PIPX_BIN_DIR=str(bin_dir),
                PIPX_MAN_DIR=str(root / "man"),
            )
            command = ["uv", "tool", "run", "--from", "pipx==1.19.1", "pipx", "install"]
        subprocess.run(
            [*command, "--python", sys.executable, str(artifact.resolve())],
            env=env,
            check=True,
        )
        env["DRIFT_TEST_EXECUTABLE"] = str(
            bin_dir / ("drift.exe" if os.name == "nt" else "drift")
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/integration/test_console_contract.py",
            ],
            env=env,
            check=True,
        )


if __name__ == "__main__":
    main()
