# Isolated simulated users and journey-first exploration

A downstream derivative of Chaosfolk went through its own security reviews and field
tests. This change brings the findings that apply here back into the engine. Two themes:
a simulated user can no longer reach beyond its own browser, and an exploration starts
with the business journey instead of leaving it to chance.

## What changes for you

- **Users run a separate command.** Sheets call `python -P -m chaosfolk.user --key KEY h01 look`
  instead of `chaosfolk h01 look`. That command accepts only user actions and refuses every
  leader command, so you can approve it once for a whole session without approving
  `serve --app-command` or `replay`. Run `chaosfolk sheets` again after upgrading; `chaosfolk humans`
  prints the command of each user, which is how the coordinator plays the scout. With the leader
  token set, plain `chaosfolk e0 look` still works for the coordinator.
- **One key per user.** The engine refuses an action whose key is not the key of the user it
  targets: a page that tricks one user cannot make it act in another user's browser or end
  its session.
- **Tighter limits.** `goto` and `tab new` stay on the origin of `launch --url` (an app's own
  redirects still work), a user keeps at most 20 downloads, `save-state` refuses a path under
  `uploads/`, and the fault plan (`faults`) is a leader command.
- **Quoting that cannot run code.** Sheets ask for texts between straight single quotes. A
  promo code typed as `"$(...)"` between double quotes used to be run by the shell.
- **Safer reports and scenarios.** A report no longer includes the `--app-command` text, a replay
  start must be an HTTP(S) address, and a proof file is read only from inside the session folder.
- **Safer git and installs.** git no longer fetches or runs a transport command declared by a
  received `.git`, `chaos schedule add` registers a job disabled and prints the command to read,
  and `install-browser` runs `python -P -m playwright` so the tested project cannot shadow it.

## What you can now do

- **Cover a journey first.** [docs/journey.md](../journey.md) describes how to map the steps and
  modes of a multi-step journey and play a matrix with directed testers: straight journeys,
  switching mode after and in the middle of a step, finishing in one mode and validating in
  the other. A human tester found five defects on a two-mode quote app that a Deep audit had
  missed; the benchmark now includes a seeded version of the main one, `mode-switch-step-skip`.
- **Wait for a slow assistant.** A user's file can set `attente_max` (cumulative seconds of
  `wait`, 60 by default, up to 1800). `draw` keeps hand-written users when it replaces the
  drawn ones.
- **Tag findings.** A finding can carry a `type` (`ui`, `ux`, `technique`, `accessibilite`,
  `contenu`, `performance`), shown beside its severity in the report.

## Limits

- Per-user keys separate users at the engine protocol. Agents that share an operating-system
  account can still read the same files.
- The same-origin rule also applies to the scout. Test an app that needs a second origin
  through its own links, or start another session for that origin.
- The journey guide is a method for a coordinator, not a guarantee: it was written from one
  case, and the matrix is only as complete as the map drawn during reconnaissance.
