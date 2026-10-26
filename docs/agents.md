# Install the agent skill

The engine is a Python package. The skill tells your coding agent how to plan an
exploration, delegate users and judge evidence. Install both.

## Shared engine setup

Use Python 3.12+, a virtual environment and the README's `pip install .` commands.
Run `chaosfolk check` in the same shell the agent will use. If PATH does not expose
the command, activate the virtual environment or use its Python with
`-m chaosfolk`. The skill installer does not install Python dependencies.

## Skill installer

```bash
npx skills add loukan42/chaosfolk --skill chaosfolk
```

Node.js and npm are required for `npx`. Choose your host and installation scope in the installer. This uses the external
[Skills CLI](https://github.com/vercel-labs/skills). Its telemetry is separate from
the Chaosfolk engine; consult its documentation for `DISABLE_TELEMETRY=1`.

## Manual installation

Copy this repository's `SKILL.md`, `README.md` and `docs/` together into the host's skill folder.
For Codex, the default user location is `~/.codex/skills/chaosfolk/`; for Claude
Code it is `~/.claude/skills/chaosfolk/`. Keep the relative `docs/` links intact.
The Python package still needs a separate install into the shell's environment.

For other hosts, use their documented skill directory or attach `SKILL.md` and
its linked guides to the coordinator. The host must support file reads, a shell
and user-authorized browser interaction. Parallel simulated users additionally
require subagents. Sequential personas reduce independence; disclose that scope.

## Claude Code

The optional dedicated definition limits the user subagent's available tools:

```bash
chaosfolk install-agent
```

It writes `~/.claude/agents/chaosfolk-user.md`. Existing custom definitions are
preserved by default. `--force` explicitly replaces one and saves a backup.
Choose the host's configured model; the definition does not pin a provider model.
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
