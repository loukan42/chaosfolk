"""Where an audit runs. Both backends start an audit, report its state and hand back the report archive.

- `SandboxBackend`: a Vercel Sandbox microVM restored from the prepared snapshot (see web/sandbox/).
- `DemoBackend`: the offline Chaosfolk demo in a local thread, for development and tests. It ignores the URL.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

from . import pack

SANDBOX_ROOT = "/opt/chaosfolk"
SANDBOX_ZIP = f"{SANDBOX_ROOT}/work/report.zip"
# The sandbox firewall refuses these destinations even though every public domain is allowed.
PRIVATE_RANGES = ("0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
                  "192.0.0.0/24", "192.168.0.0/16", "198.18.0.0/15", "224.0.0.0/4", "240.0.0.0/4",
                  "::1/128", "fc00::/7", "fe80::/10")


class BackendError(Exception):
    pass


class DemoBackend:
    def __init__(self):
        self.jobs = {}

    def start(self, settings, audit):
        work = Path(tempfile.mkdtemp(prefix="chaosfolk-demo-"))
        job = {"state": "running", "error": "", "zip": work / "report.zip"}
        self.jobs[audit["id"]] = job

        def run():
            try:
                subprocess.run([sys.executable, "-m", "chaosfolk", "demo", "--output", str(work / "run"),
                                "--lang", audit["lang"]], capture_output=True, timeout=600, check=False)
                pack.build(work / "run", job["zip"], pack.archive_name(audit["host"], audit["created_at"]), audit["url"])
                job["state"] = "done"
            except Exception as error:  # reported to the visitor as a failed audit
                job["state"], job["error"] = "failed", str(error) or "The demo failed."

        threading.Thread(target=run, daemon=True).start()
        return json.dumps({"job": audit["id"]})

    def poll(self, handle):
        job = self.jobs.get(json.loads(handle)["job"])
        if job is None:
            return "failed", "The server restarted during the audit."
        return job["state"], job["error"]

    def collect(self, handle):
        return self.jobs[json.loads(handle)["job"]]["zip"].read_bytes()

    def stop(self, handle):
        self.jobs.pop(json.loads(handle)["job"], None)


class SandboxBackend:
    def __init__(self, sdk=None):
        if sdk is None:
            from vercel.sandbox import sync as sdk
        self.sdk = sdk

    def policy(self, settings):
        sdk = self.sdk
        rules = {"*": []}
        if settings.broker_key:
            rules["openrouter.ai"] = [sdk.NetworkPolicyRule(transform=[sdk.NetworkPolicyTransform(
                headers={"Authorization": f"Bearer {settings.openrouter_key}"})])]
        return sdk.NetworkPolicy.custom(allow=rules, subnets=sdk.NetworkPolicySubnets(deny=PRIVATE_RANGES))

    def start(self, settings, audit):
        if not settings.snapshot_id:
            raise BackendError("No sandbox snapshot is configured on the server.")
        if not settings.model or not settings.openrouter_key:
            raise BackendError("No model is configured on the server.")
        sdk = self.sdk
        box = sdk.create_sandbox(
            source=sdk.SnapshotSource(snapshot_id=settings.snapshot_id),
            resources=sdk.SandboxResources(vcpus=settings.vcpus),
            # Hobby sessions stop after 45 minutes; the engine limit is far below.
            execution_time_limit=min(settings.audit_seconds + 900, 2700),
            persistent=False,
            network_policy=self.policy(settings),
            tags={"app": "chaosfolk-web"},
        )
        env = {
            "PATH": f"{SANDBOX_ROOT}/venv/bin:{SANDBOX_ROOT}/npm/bin:/usr/local/bin:/usr/bin:/bin",
            "PLAYWRIGHT_BROWSERS_PATH": f"{SANDBOX_ROOT}/browsers",
            "CHAOSFOLK_MODEL": settings.model,
            # With brokering, the firewall replaces this placeholder on requests to openrouter.ai.
            "OPENROUTER_API_KEY": "brokered-by-sandbox-firewall" if settings.broker_key else settings.openrouter_key,
        }
        args = [audit["url"], audit["lang"], str(settings.audit_seconds), str(settings.max_actions),
                str(settings.users), audit["host"], pack.archive_name(audit["host"], audit["created_at"])]
        command = box.create_command(f"{SANDBOX_ROOT}/run-audit.sh", args, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return json.dumps({"sandbox": box.name, "command": command.id})

    def _box(self, handle):
        return self.sdk.get_sandbox(name=json.loads(handle)["sandbox"])

    def poll(self, handle):
        box = self._box(handle)
        status = str(getattr(box.status, "value", box.status) or "")
        if status in {"pending", "snapshotting"}:
            return "running", ""
        if status != "running":
            # Never touch a stopped sandbox: command calls would resume it.
            return "failed", "The audit machine stopped before the report was written."
        command = box.get_command(json.loads(handle)["command"])
        if command.returncode is None:
            return "running", ""
        if command.returncode == 0:
            return "done", ""
        return "failed", "The audit ended without a report."

    def collect(self, handle):
        missing = (FileNotFoundError, getattr(self.sdk, "SandboxPathNotFoundError", FileNotFoundError))
        try:
            return self._box(handle).fs.read_bytes(SANDBOX_ZIP)
        except missing:
            raise BackendError("The audit ended without a report.") from None

    def stop(self, handle):
        try:
            box = self._box(handle)
            box.stop()
            # Keep orphan snapshots: the prepared snapshot this sandbox started from would count as one.
            box.destroy()
        except Exception:
            pass
