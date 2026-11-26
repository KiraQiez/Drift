# Drift

**Your code hasn't changed. Your environment has.**

Drift (Development Environment Version Control) is a developer CLI. Git tracks changes to your source code. Drift is designed to help you find changes in the environment around it, such as a new runtime version, a changed lockfile, or a Docker service that stopped.

Drift captures local snapshots, shows what changed, and verifies the current environment against a known-working baseline. It tracks environment variable names and file declarations while leaving values out of snapshots and reports.

## Workflow

```sh
drift init
drift snapshot -m "Working environment"
drift history
drift baseline set a81f23
drift diff
drift verify --json
```

Use the snapshot ID or a unique prefix from your own history when setting a baseline. A verification exits with code `0` for a match, `3` for confirmed drift, and `4` for incomplete coverage. See the [CLI specification](docs/CLI_SPEC.md) for the full contract.

## Installation

Choose one installer. Homebrew is available on macOS.

```sh
brew install KiraQiez/tap/drift
uv tool install drift-dev-env
pipx install drift-dev-env
```

Run `drift --version` to verify the installation.

## Development

From a checkout with uv and Just available, run the commands below. Use `uv run --locked drift` in place of `drift` when working directly from the checkout.

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
