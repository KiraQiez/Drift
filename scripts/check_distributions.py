"""Validate the contents and identity of the wheel and source distribution."""

import argparse
import configparser
import hashlib
import tarfile
import tomllib
from email import policy
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

from packaging.requirements import Requirement


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_metadata(data, project):
    metadata = BytesParser(policy=policy.default).parsebytes(data)
    for field, key in (
        ("Name", "name"),
        ("Version", "version"),
        ("Requires-Python", "requires-python"),
        ("License-Expression", "license"),
    ):
        if metadata[field] != project[key]:
            raise ValueError(f"Unexpected {field}: {metadata[field]}")
    if {Requirement(value) for value in metadata.get_all("Requires-Dist", [])} != {
        Requirement(value) for value in project["dependencies"]
    }:
        raise ValueError("Unexpected runtime dependency metadata")
    if metadata.get_all("License-File") != project["license-files"]:
        raise ValueError("Unexpected license files")
    if set(metadata.get_all("Project-URL", [])) != {
        f"{label}, {url}" for label, url in project["urls"].items()
    }:
        raise ValueError("Unexpected project URLs")


def check_contents(actual, expected):
    if actual != expected:
        raise ValueError(
            f"Unexpected archive contents. Extra: {actual - expected}; "
            f"missing: {expected - actual}"
        )


def validate(wheel, sdist, project):
    package = {p.as_posix() for p in Path("src/drift").rglob("*.py")}
    license_bytes = Path("LICENSE").read_bytes()
    info = wheel.name.removesuffix("-py3-none-any.whl") + ".dist-info"
    wheel_metadata = {
        "METADATA",
        "WHEEL",
        "entry_points.txt",
        "licenses/LICENSE",
        "RECORD",
    }
    with ZipFile(wheel) as archive:
        check_contents(
            set(archive.namelist()),
            {name.removeprefix("src/") for name in package}
            | {f"{info}/{name}" for name in wheel_metadata},
        )
        check_metadata(archive.read(f"{info}/METADATA"), project)
        headers = BytesParser(policy=policy.default).parsebytes(
            archive.read(f"{info}/WHEEL")
        )
        if headers["Root-Is-Purelib"] != "true" or headers.get_all("Tag") != [
            "py3-none-any"
        ]:
            raise ValueError("Unexpected wheel platform tag")
        scripts = configparser.ConfigParser()
        scripts.read_string(archive.read(f"{info}/entry_points.txt").decode())
        if dict(scripts["console_scripts"]) != project["scripts"]:
            raise ValueError("Unexpected console entry points")
        if archive.read(f"{info}/licenses/LICENSE") != license_bytes:
            raise ValueError("Incorrect wheel license")
        for name in package:
            if archive.read(name.removeprefix("src/")) != Path(name).read_bytes():
                raise ValueError(f"Incorrect wheel source: {name}")

    root = sdist.name.removesuffix(".tar.gz")
    included = package | {
        "LICENSE",
        "README.md",
        "pyproject.toml",
        "PKG-INFO",
        ".gitignore",
    }
    with tarfile.open(sdist) as archive:
        members = archive.getmembers()
        check_contents(
            {member.name for member in members}, {f"{root}/{name}" for name in included}
        )
        if not all(member.isfile() for member in members):
            raise ValueError("The sdist must contain regular files only")
        for name in included:
            with archive.extractfile(f"{root}/{name}") as stream:
                data = stream.read()
            if name == "PKG-INFO":
                check_metadata(data, project)
            elif data != Path(name).read_bytes():
                raise ValueError(f"Incorrect sdist input: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--verify", action="store_true", help="Check recorded hashes")
    args = parser.parse_args()

    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    stem = f"{project['name'].replace('-', '_')}-{project['version']}"
    wheel = args.directory / f"{stem}-py3-none-any.whl"
    sdist = args.directory / f"{stem}.tar.gz"
    sums = args.directory / "SHA256SUMS"
    expected = {wheel.name, sdist.name}
    if args.verify:
        expected.add(sums.name)
    check_contents({path.name for path in args.directory.iterdir()}, expected)
    record = "".join(f"{digest(path)}  {path.name}\n" for path in (wheel, sdist))
    if args.verify:
        if sums.read_text(encoding="ascii") != record:
            raise ValueError("Distribution hashes do not match SHA256SUMS")
    else:
        validate(wheel, sdist, project)
        sums.write_text(record, encoding="ascii", newline="\n")
    print(record, end="")


if __name__ == "__main__":
    main()
