# Changelog

## Unreleased

## 0.2.0

- Add `drift snapshot --baseline` to set up a project and save its baseline in one command.
- Make comparison reports easier to scan and add `--details` for full hashes and Git context.
- Scope Homebrew workflow checks to the Drift formula.

## 0.1.0

- Capture local development environment snapshots covering runtimes, dependency manifests, environment declarations, and local tool availability.
- Set a known-working baseline and compare the current environment against it with human-readable or JSON output.
- Support Python 3.12 and newer. Snapshots and baselines use schema version 1.
