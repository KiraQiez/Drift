# Drift

**Your code hasn't changed. Your environment has.**

Drift (Development Environment Version Control) is a developer CLI in early development. Git tracks changes to your source code. Drift is designed to help you find changes in the environment around it, such as a new runtime version, a changed lockfile, or a Docker service that stopped.

The planned MVP captures local snapshots, shows what changed, and verifies the current environment against a known-working baseline. It will track environment variable names and file declarations while leaving values out of snapshots and reports.

## Planned workflow

```sh
drift init
drift snapshot -m "Working environment"
drift history
drift baseline set a81f23
drift diff
drift verify --json
```

Use the snapshot ID or a unique prefix from your own history when setting a baseline. See the [CLI specification](docs/CLI_SPEC.md) for the planned command behavior.

## Installation plans

These commands illustrate the planned installation methods once packages are published and the placeholders have been replaced.

```sh
brew install OWNER/tap/drift
uv tool install PACKAGE_NAME
pipx install PACKAGE_NAME
```

## Development

The current CLI provides root help and version output. Run these commands from a checkout with uv and Just available.

```sh
just setup
uv run --locked drift --help
uv run --locked drift --version
just check
```

See the [development guide](docs/DEVELOPMENT.md) for contributor commands and the [roadmap](docs/ROADMAP.md) for implementation status.

## Documentation

| If you want to understand… | Read |
| --- | --- |
| Who Drift is for and what the MVP covers | [Product requirements](docs/PRD.md) |
| How to use commands and interpret their output | [CLI specification](docs/CLI_SPEC.md) |
| How the components fit together and why | [Architecture](docs/ARCHITECTURE.md) |
| How configuration, snapshots, and comparison work | [Data model](docs/DATA_MODEL.md) |
| What Drift collects and how it protects local state | [Security and privacy](docs/SECURITY.md) |
| How to keep commits focused and code maintainable | [Contribution rules](RULES.md) |
| How to develop and test Drift | [Development guide](docs/DEVELOPMENT.md) |
| What is planned and what is complete | [Roadmap and task checklist](docs/ROADMAP.md) |
| How Drift is packaged and published | [Release and distribution](docs/RELEASE.md) |

The `docs/` directory serves contributors and AI agents. [AGENTS.md](AGENTS.md) directs AI agents to their workflow in `.ai/rules/`.

Drift is licensed under the [Apache License 2.0](LICENSE).
