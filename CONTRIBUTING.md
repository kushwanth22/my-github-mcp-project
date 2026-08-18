# Contributing to GitHub MCP Gateway

Thanks for your interest in contributing! This guide covers how to set up your
dev environment and submit changes.

## Prerequisites

- Python 3.11+
- Node.js 20+ (required by the upstream `@modelcontextprotocol/server-github` subprocess)
- [uv](https://docs.astral.sh/uv/) for Python dependency management
- [ngrok](https://ngrok.com) for local OAuth/webhook testing
- [GitHub CLI (`gh`)](https://cli.github.com/) — used by the `make pr*` targets

## Setup

1. Fork the repository and clone your fork:

   ```bash
   git clone https://github.com/<your-username>/my-github-mcp-project.git
   cd my-github-mcp-project
   ```

2. Install dependencies:

   ```bash
   make install
   ```

3. Copy the environment template and fill in your own values:

   ```bash
   cp .env.example .env
   ```

   You'll need at minimum a `GITHUB_TOKEN` (PAT) for the upstream GitHub MCP
   server. See the README's [Environment variables](README.md#environment-variables)
   table for the full list.

4. (Optional) Install the pre-commit hook so lint/format checks run automatically:

   ```bash
   make install-hooks
   ```

5. Start the gateway locally:

   ```bash
   make dev      # gateway + ngrok tunnel
   # or
   make run      # gateway only, on :8000
   ```

## Making changes

- Create a branch for your change:

  ```bash
  git checkout -b my-feature
  ```

- Keep changes focused — one logical change per PR.
- Follow existing project structure:
  - Gateway/server code → `gateway/`
  - New connectors → `gateway/connectors/` (subclass `MCPConnector`, see `github.py`)
  - New custom tools → `gateway/tools/<connector>/` (see `README.md#adding-a-custom-tool`)
  - Agent/orchestrator logic → `agents/`
  - Standalone CLI scripts → `scripts/`

## Code style

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
make lint      # check for lint errors
make format    # auto-format code
make check     # lint + format check (no changes made)
```

Run `make pre-commit` before committing to make sure everything passes:

```bash
make pre-commit
```

If you installed hooks via `make install-hooks`, this runs automatically on
every `git commit`.

## Submitting a pull request

1. Commit your changes with a clear, descriptive message.
2. Push your branch and open a PR. If you have `gh` installed and configured,
   you can use the built-in helper, which runs checks first and then creates
   the PR:

   ```bash
   make pr
   ```

   Otherwise, push your branch and open a PR manually against `master` on GitHub.

3. In your PR description, include:
   - What the change does and why
   - Any manual testing performed (e.g., ran `make dev` and exercised the
     affected endpoint/tool)
   - Related issue number, if any (e.g., `Closes #4`)

4. Ensure CI/lint checks pass and address review feedback.

5. Once approved, a maintainer will merge using:

   ```bash
   make pr-merge
   ```

   which squash-merges and deletes the branch.

## Reporting bugs / requesting features

Please open a GitHub issue with:

- A clear description of the problem or request
- Steps to reproduce (for bugs)
- Relevant logs/environment details (Python/Node version, OS)

## Questions

If anything in this guide is unclear or out of date, feel free to open an
issue or PR to improve it.
