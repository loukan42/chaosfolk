# Security

Chaosfolk controls a real browser and can run a local development command. Use it
only on systems you own or are authorized to test, with synthetic data. Run it in
a disposable environment with the minimum permissions required.

The engine listens on loopback and authenticates commands with session tokens.
Leader and user tokens separate roles inside the protocol; they do not sandbox
agents that share an operating-system account. Those agents may be able to read
the state directory, change files or run other commands outside the engine.

The skill constrains scope and treats page content as untrusted. The engine allows
HTTP(S) navigation and does not enforce a network-origin allowlist. A malicious app
can navigate to external sites. Use network isolation if target confinement is
required. The engine is not a secure environment for arbitrary hostile websites.

The `inspect` command and `js` assertions execute JavaScript in the test browser.
Review scenarios before replaying files from another person. App startup commands
run locally with your permissions. Persona IDs and upload paths are validated, but
the entire session folder should still be treated as private evidence.

The optional `probe` command accepts loopback URLs only. It blocks requests to
other origins, non-GET/HEAD browser requests, service workers and WebSockets.
It limits clients and rounds, but each navigation may load multiple resources.
GET handlers can still change application state. Run it against a disposable test
application; it is not a security sandbox or a production load test.

Reports are local HTML with embedded text data. They load only relative screenshot
paths; they do not fetch external fonts or scripts. Screenshots, URLs and user
reactions may contain private app data. Review all artifacts before publishing.

Report vulnerabilities privately through the repository's GitHub Security tab
when private reporting is available. Otherwise open an issue asking for a private
contact without including exploit details or sensitive artifacts.
