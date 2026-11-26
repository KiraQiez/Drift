"""Render the tap formula from a verified release sdist and exported lockfile."""

import argparse
import json
import re
import tomllib
from pathlib import Path
from string import Template
from urllib.parse import urlsplit

from check_distributions import digest
from packaging.markers import Marker
from packaging.tags import compatible_tags, cpython_tags, mac_platforms
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

PYTHON = (3, 14)
PYTHON_MINOR = ".".join(map(str, PYTHON))


def pypi_filename(url: str) -> str:
    target = urlsplit(url)
    if (
        target.scheme != "https"
        or target.netloc != "files.pythonhosted.org"
        or target.query
        or target.fragment
        or not re.fullmatch(r"/packages/[a-zA-Z0-9./_%+-]+", target.path)
    ):
        raise ValueError(f"Expected a PyPI file URL: {url}")
    return target.path.rsplit("/", 1)[-1]


def locked_wheels(packages: list[dict], arch: str) -> dict[str, tuple[str, str]]:
    platforms = list(mac_platforms((14, 0), arch))
    tags = {
        tag: position
        for position, tag in enumerate(
            [
                *cpython_tags(PYTHON, platforms=platforms),
                *compatible_tags(PYTHON, platforms=platforms),
            ]
        )
    }
    environment = {
        "implementation_name": "cpython",
        "implementation_version": f"{PYTHON_MINOR}.0",
        "os_name": "posix",
        "platform_machine": arch,
        "platform_python_implementation": "CPython",
        "platform_release": "23.0.0",
        "platform_system": "Darwin",
        "platform_version": "Darwin Kernel Version 23.0.0",
        "python_full_version": f"{PYTHON_MINOR}.0",
        "python_version": PYTHON_MINOR,
        "sys_platform": "darwin",
    }
    selected = {}
    for package in packages:
        if "marker" in package and not Marker(package["marker"]).evaluate(environment):
            continue
        name = package["name"]
        wheels = []
        for wheel in package.get("wheels", []):
            url = wheel["url"]
            wheel_name, version, _, wheel_tags = parse_wheel_filename(
                pypi_filename(url)
            )
            if wheel_name != canonicalize_name(name) or version != Version(
                package["version"]
            ):
                raise ValueError(f"Incorrect wheel identity for {name}")
            compatible = wheel_tags & tags.keys()
            if compatible:
                checksum = wheel["hashes"]["sha256"]
                if not re.fullmatch(r"[0-9a-f]{64}", checksum):
                    raise ValueError(f"Invalid wheel checksum for {name}")
                wheels.append((min(tags[tag] for tag in compatible), url, checksum))
        if name in selected or not wheels:
            raise ValueError(
                f"Expected a unique compatible locked {name} on macOS {arch}"
            )
        _, url, checksum = min(wheels)
        selected[name] = (url, checksum)
    return selected


def resource(name: str, wheel: tuple[str, str], indent: str = "  ") -> str:
    url, checksum = wheel
    return (
        f'{indent}resource "{name}" do\n'
        f'{indent}  url "{url}", using: :nounzip\n'
        f'{indent}  sha256 "{checksum}"\n'
        f"{indent}end"
    )


def render_resources(packages: list[dict]) -> str:
    arm = locked_wheels(packages, "arm64")
    intel = locked_wheels(packages, "x86_64")
    blocks = []
    for name in sorted(arm.keys() | intel.keys()):
        if name in arm and arm[name] == intel.get(name):
            blocks.append(resource(name, arm[name]))
        else:
            for platform, wheels in (("arm", arm), ("intel", intel)):
                if name in wheels:
                    blocks.append(
                        f"  on_{platform} do\n{resource(name, wheels[name], '    ')}\n  end"
                    )
    return "\n\n".join(blocks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdist", type=Path)
    parser.add_argument("lock", type=Path, help="uv's exported pylock.toml")
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-url", help="PyPI URL for these exact source bytes")
    args = parser.parse_args()

    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    filename = f"{project['name'].replace('-', '_')}-{project['version']}.tar.gz"
    if args.sdist.name != filename:
        parser.error(f"Expected the source archive {filename}")
    if args.source_url and pypi_filename(args.source_url) != filename:
        parser.error(f"PyPI URL must identify {filename}")

    packages = tomllib.loads(args.lock.read_text(encoding="utf-8"))["packages"]
    template = Template(
        Path("packaging/homebrew/drift.rb.in").read_text(encoding="utf-8")
    )
    formula = template.substitute(
        description=json.dumps(project["description"].removesuffix(".")),
        homepage=json.dumps(project["urls"]["Homepage"]),
        source_url=json.dumps(args.source_url or args.sdist.resolve().as_uri()),
        version=json.dumps(project["version"]),
        checksum=json.dumps(digest(args.sdist)),
        license=json.dumps(project["license"]),
        python=PYTHON_MINOR,
        resources=render_resources(packages),
    )
    args.output.write_text(formula, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
