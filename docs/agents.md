# Install the agent skill

The engine is a Python package. The skill tells your coding agent how to plan an
exploration, delegate users and judge evidence. The installer sets up both:

```bash
curl -LsSf https://raw.githubusercontent.com/loukan42/chaosfolk/main/install.sh | CHAOSFOLK_VERSION=0.8.0 CHAOSFOLK_SHA256=d04d7800059d7ff1cdc2e9ae5b4d591f061e84c8d7752a921b92b815845f6460 sh
```

```powershell
$env:CHAOSFOLK_VERSION = '0.8.0'; $env:CHAOSFOLK_SHA256 = 'd04d7800059d7ff1cdc2e9ae5b4d591f061e84c8d7752a921b92b815845f6460'
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/loukan42/chaosfolk/main/install.ps1 | iex"
```

It installs a pinned [uv](https://docs.astral.sh/uv/) when missing, downloads
the release archive, verifies its SHA-256 when `CHAOSFOLK_SHA256` is set,
installs the engine with `uv tool install` (uv provides Python 3.12+ if needed),
then runs `chaosfolk setup`. `CHAOSFOLK_SOURCE` installs from another archive,
path or internal mirror, `CHAOSFOLK_REQUIRE_UV=1` refuses to download uv, and
`CHAOSFOLK_NO_MODIFY_PATH=1` leaves PATH unchanged. The checksum of each release
archive is published in its release notes.

## chaosfolk setup

`setup` makes sure a usable browser exists, downloading Chromium for the engine's
Python if none is found. It then copies the skill, `SKILL.md` and its guides, into
the global skills folder of every agent found in your home folder:

| Agent | `--agent` | Found when this exists | Skill folder |
| --- | --- | --- | --- |
| Claude Code | `claude-code` | `~/.claude` | `~/.claude/skills/chaosfolk` |
| Codex | `codex` | `~/.codex` | `~/.agents/skills/chaosfolk` |
| Cursor | `cursor` | `~/.cursor` | `~/.cursor/skills/chaosfolk` |
| GitHub Copilot | `github-copilot` | `~/.copilot` | `~/.copilot/skills/chaosfolk` |
| Gemini CLI | `gemini-cli` | `~/.gemini` | `~/.gemini/skills/chaosfolk` |
| OpenCode | `opencode` | `~/.config/opencode` | `~/.config/opencode/skills/chaosfolk` |
| Windsurf | `windsurf` | `~/.codeium/windsurf` | `~/.codeium/windsurf/skills/chaosfolk` |
| Others | `universal` | used when no agent is found | `~/.agents/skills/chaosfolk` |

The folders follow the [Skills CLI table](https://github.com/vercel-labs/skills/blob/main/docs/agents.md).
`--agent` (repeatable) limits the installation to the agents you name, and
`--skip-browser` skips the browser step. Running `setup` again refreshes the
skill after an update. It replaces a folder only when it holds the Chaosfolk
skill, including a link left by `npx skills add`; another skill with the same
folder name is left alone and reported.

## Other installers

`pipx install git+https://github.com/loukan42/chaosfolk.git` or
`uv tool install git+https://github.com/loukan42/chaosfolk.git`, followed by
`chaosfolk setup`, give the same result. If you install into a virtual
environment instead, the agent's shell must activate it or call its Python with
`-m chaosfolk`. `install-browser` always downloads Chromium for the Python that
runs the engine.

The [Skills CLI](https://github.com/vercel-labs/skills) can install the skill
alone, for the agents it supports:

```bash
npx skills add loukan42/chaosfolk --skill chaosfolk -g -a claude-code
```

It needs Node.js 22.20 or newer and does not install the engine. Its telemetry
is separate from Chaosfolk; consult its documentation for `DISABLE_TELEMETRY=1`.

## Manual installation

Copy `SKILL.md` and the `docs/` guides it links together into the host's skill
folder, keeping the relative `docs/` links intact. For other hosts, use their
documented skill directory or attach `SKILL.md` and its linked guides to the
coordinator. The host must support file reads, a shell and user-authorized
browser interaction. Parallel simulated users additionally require subagents.
Sequential personas reduce independence; disclose that scope.

## Claude Code

`setup` also writes the dedicated simulated user definition, which limits the
user subagent's tools, to `~/.claude/agents/chaosfolk-user.md`. A copy you edited
is kept; `chaosfolk install-agent --force` replaces it and saves a backup.
The definition runs users on Sonnet, which costs less than the coordinator's
model and is enough to read screens and act. Edit its `model:` line to change it.
Some hosts discover new agents only when starting a new session.

Claude Code's Windows shell is commonly Git Bash. Generate its sheets with
`chaosfolk sheets ... --shell posix`. Codex with PowerShell uses
`--shell powershell`. The engine defaults to PowerShell on Windows and POSIX on
other systems; override it to match the actual shell.

## Credentials and concurrent sessions

`launch` prints a leader token. Set `CHAOSFOLK_LEADER_TOKEN` in the coordinator's
environment for `humans`, `fault`, `fault-end`, `inspect`, `save-state` and `stop`.
Do not give that token to simulated users. This protocol separation is not an OS
sandbox: agents sharing a user account can access the same files.

For independent concurrent engine sessions, choose a different state directory:

```bash
chaosfolk --state-dir .horde/state-a launch --url http://localhost:3000 --folder .horde/run-a
```

Pass the same `--state-dir` to subsequent commands. Generated sheets include its
absolute path. Alternatively set `CHAOSFOLK_HOME` before starting the coordinator
and inherit it in child processes. A state directory can host one engine at a time.

## Compatibility claims

The CLI and browser protocol are exercised in automated tests. The full skill
workflow depends on the host's model, permissions and delegation tools. Host-wide
end-to-end compatibility is not established by the browser tests alone. Report
your host version and observed failure when an adaptation is needed.
