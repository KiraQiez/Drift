"""Verify a release ref and extract its changelog section."""

import argparse
import re
import tomllib
from pathlib import Path

RELEASE_TAG = re.compile(
    r"refs/tags/v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
)


def extract_notes(ref: str, version: str, changelog: str) -> str:
    if ref == "refs/heads/staging":
        heading = "Unreleased"
    else:
        match = RELEASE_TAG.fullmatch(ref)
        if match is None:
            raise ValueError("Expected staging or a stable vMAJOR.MINOR.PATCH tag")
        heading = ".".join(match.groups())
        if heading != version:
            raise ValueError(
                f"Tag version {heading} disagrees with package version {version}"
            )

    sections = re.split(r"^##[ \t]+", changelog, flags=re.MULTILINE)[1:]
    notes = []
    for section in sections:
        title, _, body = section.partition("\n")
        if title.strip() == heading:
            notes.append(body.strip())
    if len(notes) != 1 or (heading != "Unreleased" and not notes[0]):
        raise ValueError(
            f"Expected one changelog section for {heading} with release notes"
        )
    return notes[0] + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ref")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    try:
        notes = extract_notes(
            args.ref,
            project["version"],
            Path("CHANGELOG.md").read_text(encoding="utf-8"),
        )
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    args.output.write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
