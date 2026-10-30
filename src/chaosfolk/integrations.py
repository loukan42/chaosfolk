"""Optional QA adapters. External tools and test environments remain explicit."""
import argparse
import asyncio
import csv
import hashlib
import io
from contextlib import suppress
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from email import policy
from email.parser import BytesParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


MAX_BYTES = 8 * 1024 * 1024
MAX_LOG_BYTES = 16 * 1024 * 1024


def read_bytes(path, limit=MAX_BYTES):
    with Path(path).open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Input exceeds the size limit')
    return data


def origin(url):
    parts = urlsplit(url)
    if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password:
        raise ValueError('Use an HTTP(S) address without embedded credentials')
    port = parts.port or (443 if parts.scheme == 'https' else 80)
    host = parts.hostname.lower()
    return f'{parts.scheme}://{("[" + host + "]") if ":" in host else host}:{port}'


def allowed_origin(url, extra=()):
    target = origin(url)
    host = urlsplit(url).hostname.lower()
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host == 'localhost'
    if not local and target not in {origin(item) for item in extra}:
        raise ValueError('Remote target needs an explicit --allow-origin')
    return target


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect refused; specify the final test endpoint explicitly')


def get_bytes(url, timeout=10):
    # Proxies and redirects could send local test traffic to an unrelated server.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(url, headers={'Accept': 'application/json, text/plain'})
    try:
        with opener.open(request, timeout=timeout) as response:
            data = response.read(MAX_BYTES + 1)
    except (HTTPError, URLError) as error:
        raise ValueError('Could not read the test endpoint') from error
    if len(data) > MAX_BYTES:
        raise ValueError('Endpoint response exceeds the size limit')
    return data


def mailpit(base, message=None, subject=None, contains=(), recipient=None, limit=20, allow=()):
    """Read a list or raw RFC822 source. Never send, release, delete or mark read."""
    allowed_origin(base, allow)
    parts = urlsplit(base)
    if parts.query or parts.fragment or parts.path not in {'', '/'}:
        raise ValueError('Mailpit URL must be an origin, without a path or query')
    if not 1 <= limit <= 100:
        raise ValueError('Limit must be between 1 and 100')
    base = base.rstrip('/')
    if message is None:
        if subject is not None or contains or recipient is not None:
            raise ValueError('Choose a --message ID before checking its content')
        data = json.loads(get_bytes(base + '/api/v1/messages?' + urlencode({'limit': limit})))
        items = data.get('messages')
        if not isinstance(items, list):
            raise ValueError('Unexpected Mailpit message list')
        # Do not expose bodies, recipients or reset links just to choose a message.
        return {'adapter': 'mailpit', 'status': 'listed', 'messages': [
            {'id': str(item.get('ID', ''))[:128], 'subject': str(item.get('Subject', ''))[:200]}
            for item in items[:limit] if isinstance(item, dict)], 'limit': limit}
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', message):
        raise ValueError('Invalid message ID')
    if subject is None and not contains and recipient is None:
        raise ValueError('Supply at least one message expectation')
    raw = get_bytes(base + '/api/v1/message/' + message + '/raw')
    mail = BytesParser(policy=policy.default).parsebytes(raw)
    body = []
    for part in mail.walk():
        if part.get_content_type() in {'text/plain', 'text/html'} and part.get_content_disposition() != 'attachment':
            content = part.get_content()
            body.append(content if isinstance(content, str) else content.decode('utf-8', errors='replace'))
    checks = {}
    if subject is not None:
        checks['subject'] = str(mail.get('Subject', '')) == subject
    if recipient is not None:
        addresses = [address.addr_spec for header in mail.get_all('To', []) for address in header.addresses]
        checks['recipient'] = recipient.casefold() in {address.casefold() for address in addresses}
    for index, expected in enumerate(contains, 1):
        checks[f'contains_{index}'] = expected in '\n'.join(body)
    return {'adapter': 'mailpit', 'status': 'passed' if all(checks.values()) else 'failed',
            'checks': checks, 'sha256': hashlib.sha256(raw).hexdigest()}


def check_file(path, kind='auto', contains=(), columns=(), min_rows=None, max_rows=None):
    """Inspect a downloaded fixture without executing it or echoing its contents."""
    source = Path(path)
    raw = read_bytes(source)
    kind = source.suffix.lower().lstrip('.') if kind == 'auto' else kind
    if kind not in {'csv', 'txt', 'text', 'pdf'}:
        raise ValueError('Choose csv, text or pdf')
    if min_rows is not None and min_rows < 0 or max_rows is not None and max_rows < 0:
        raise ValueError('Row bounds cannot be negative')
    if min_rows is not None and max_rows is not None and min_rows > max_rows:
        raise ValueError('Minimum rows exceeds maximum rows')
    if kind != 'csv' and (columns or min_rows is not None or max_rows is not None):
        raise ValueError('Column and row expectations require a CSV file')
    if not contains and not columns and min_rows is None and max_rows is None:
        raise ValueError('Supply at least one file expectation')
    checks, metadata = {}, {}
    if kind == 'pdf':
        if not raw.startswith(b'%PDF-'):
            raise ValueError('File is not a PDF')
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise ValueError('PDF checks need the optional pypdf package') from error
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise ValueError('Encrypted PDFs are not supported')
        if len(reader.pages) > 200:
            raise ValueError('PDF exceeds 200 pages')
        text_parts = []
        for page in reader.pages:
            contents = page.get_contents()
            encoded = getattr(contents, '_data', b'')
            if isinstance(encoded, (bytes, bytearray)) and len(encoded) > MAX_BYTES:
                raise ValueError('PDF page content exceeds the size limit')  # Checked before decompression.
            if contents is not None and len(contents.get_data()) > MAX_BYTES:
                raise ValueError('PDF page content exceeds the size limit')
            text_parts.append(page.extract_text() or '')
            if sum(map(len, text_parts)) > MAX_BYTES:
                raise ValueError('PDF extracted text exceeds the size limit')
        text = '\n'.join(text_parts)
        metadata['pages'] = len(reader.pages)
    else:
        text = raw.decode('utf-8-sig')
    if kind == 'csv':
        reader = csv.reader(io.StringIO(text), strict=True)
        header = next(reader, [])
        if len(header) != len(set(header)):
            raise ValueError('CSV headers must be unique')
        count = 0
        for row in reader:
            if len(row) != len(header):
                raise ValueError('CSV row width differs from the header')
            count += 1
        for index, column in enumerate(columns, 1):
            checks[f'column_{index}'] = column in header
        if min_rows is not None:
            checks['min_rows'] = count >= min_rows
        if max_rows is not None:
            checks['max_rows'] = count <= max_rows
        metadata['rows'] = count
    for index, expected in enumerate(contains, 1):
        checks[f'contains_{index}'] = expected in text
    return {'adapter': 'file', 'kind': kind, 'status': 'passed' if all(checks.values()) else 'failed',
            'checks': checks, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), **metadata}


async def fulfill_read_only(route, permitted, timeout=30):
    """Fetch one authorized request; reject redirects before a second dispatch."""
    try:
        accepted = route.request.method in {'GET', 'HEAD'} and origin(route.request.url) in permitted
    except ValueError:
        accepted = False
    reason = 'Request blocked by the read-only origin policy'
    if accepted:
        response = None
        try:
            # Browser routing only intercepts the first request in a redirect
            # chain. Never continue or fulfill a redirect back to the browser.
            response = await route.fetch(max_redirects=0, max_retries=0, timeout=timeout * 1000)
            if response.status in {301, 302, 303, 307, 308}:
                reason = 'Redirect refused; specify the final test endpoint explicitly'
            else:
                await route.fulfill(response=response)
                return None
        except Exception as error:
            reason = 'Request could not be fetched: ' + str(error).split('\n')[0][:200]
        finally:
            if response is not None:
                await response.dispose()
    with suppress(Exception):
        await route.abort()
    return reason


async def axe_audit(url, script, allow=(), timeout=30):
    """Run a trusted local axe-core bundle; never load a CDN automatically."""
    target = allowed_origin(url, allow)
    permitted = {target} | {origin(item) for item in allow}
    source = read_bytes(script).decode('utf-8')
    if not 1 <= timeout <= 120:
        raise ValueError('Timeout must be between 1 and 120 seconds')
    from playwright.async_api import async_playwright
    blocked = {'requests': 0, 'reasons': []}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(service_workers='block', accept_downloads=False)
            async def guard(route):
                reason = await fulfill_read_only(route, permitted, timeout)
                if reason:
                    blocked['requests'] += 1
                    if reason not in blocked['reasons'] and len(blocked['reasons']) < 10:
                        blocked['reasons'].append(reason)
            await context.route('**/*', guard)
            await context.route_web_socket('**/*', lambda ws: ws.close())
            page = await context.new_page()
            page.set_default_timeout(timeout * 1000)
            try:
                response = await page.goto(url, wait_until='load')
            except Exception:
                if blocked['requests']:
                    return {'adapter': 'axe', 'status': 'inconclusive', 'blocked_requests': blocked['requests'],
                            'reasons': blocked['reasons'], 'script_sha256': hashlib.sha256(source.encode()).hexdigest()}
                raise
            if response is None or response.status >= 400:
                raise ValueError('Target did not load successfully')
            await page.add_script_tag(content=source)
            result = await asyncio.wait_for(page.evaluate('''async () => {
                if (!window.axe || typeof window.axe.run !== 'function') throw new Error('Missing axe.run');
                const data = await window.axe.run(document, {resultTypes:['violations','incomplete']});
                const project = rows => rows.map(r => ({id:r.id, impact:r.impact,
                    description:r.description, help:r.help, helpUrl:r.helpUrl,
                    nodes:r.nodes.map(n => ({target:n.target, failureSummary:n.failureSummary}))}));
                return {version:window.axe.version, violations:project(data.violations),
                    incomplete:project(data.incomplete)};
            }'''), timeout=timeout)
            if not isinstance(result, dict) or not isinstance(result.get('violations'), list):
                raise ValueError('Unexpected axe result')
            result.update({'adapter': 'axe', 'status': 'failed' if result['violations'] else
                           'inconclusive' if blocked['requests'] or result.get('incomplete') else 'passed',
                           'blocked_requests': blocked['requests'], 'script_sha256': hashlib.sha256(source.encode()).hexdigest(),
                           'blocked_reasons': blocked['reasons'],
                           'scope': 'Automated checks for this page state; not an accessibility conformance audit.'})
            return result
        finally:
            await browser.close()


def _kill_tree(process, owned):
    """Stop the root captured at launch; never look up an exited root by bare PID."""
    if hasattr(process, "close"):
        process.close()
        return
    import psutil
    try:
        if owned is None:
            # Popen retains the owned OS process handle (and checks child exit).
            if process.poll() is None:
                process.kill()
            return
        if not owned.is_running():
            return
        descendants = owned.children(recursive=True)
        for child in reversed(descendants):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        owned.kill()
    except psutil.NoSuchProcess:
        pass


def run_external(tool, executable, script, timeout=120):
    """Run an explicitly chosen trusted test program, without a shell."""
    if tool not in {'k6', 'appium'}:
        raise ValueError('Choose k6 or appium')
    if not 1 <= timeout <= 3600:
        raise ValueError('Timeout must be between 1 and 3600 seconds')
    executable, script = Path(executable).resolve(strict=True), Path(script).resolve(strict=True)
    if not executable.is_file() or not script.is_file():
        raise ValueError('Executable and script must be regular files')
    if executable.suffix.lower() in {'.bat', '.cmd', '.ps1', '.sh'}:
        raise ValueError('Use a native executable, not a shell wrapper')
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='chaosfolk-adapter-') as folder:
        result_path = Path(folder) / 'result.json'
        args = [str(executable), 'run', '--summary-export', str(result_path), str(script)] if tool == 'k6' else [str(executable), str(script)]
        env = dict(os.environ, CHAOSFOLK_RESULT_PATH=str(result_path))
        env.pop('CHAOSFOLK_LEADER_TOKEN', None)  # External runners never need the engine's leader credential.
        from .owned_process import OwnedProcess
        process = OwnedProcess(args, cwd=script.parent, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, bufsize=0)
        owned = None
        log_bytes = 0
        reason = None
        try:
            import psutil
            try:
                owned = psutil.Process(process.pid)
                owned.create_time()  # Capture identity before the process can exit.
            except psutil.NoSuchProcess:
                pass
            # Nonblocking pipes are supported on Windows and Unix in Python 3.12+.
            # A descendant can inherit stdout after the runner exits. A reader
            # thread followed by BufferedReader.close() could then wait forever.
            os.set_blocking(process.stdout.fileno(), False)
            while True:
                if time.monotonic() - started > timeout:
                    reason = 'timeout'
                    _kill_tree(process, owned)
                    break
                # Check for exit before reading: an empty read after exit means the runner's
                # output is complete, even when a descendant still holds the pipe open.
                exited = process.poll() is not None
                chunk = process.stdout.read(8192)  # None without data, b'' at EOF
                if chunk:
                    log_bytes += len(chunk)
                    if log_bytes > MAX_LOG_BYTES:
                        reason = 'output_limit'
                        _kill_tree(process, owned)
                        break
                elif exited:
                    break
                else:
                    time.sleep(0.05)
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=5)
        finally:
            try:
                _kill_tree(process, owned)
                with suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=5)
            finally:
                process.stdout.close()
        base = {'adapter': tool, 'exit_code': process.returncode,
                'duration_seconds': round(time.monotonic() - started, 3), 'log_bytes': log_bytes}
        if reason:
            return {**base, 'status': 'error', 'reason': reason}
        if not result_path.is_file():
            return {**base, 'status': 'inconclusive', 'reason': 'No machine-readable test result produced'}
        result = json.loads(read_bytes(result_path))
        if not isinstance(result, dict):
            raise ValueError('External result must be a JSON object')
        if tool == 'appium':
            for name in ('tests', 'failures', 'errors', 'skipped'):
                if type(result.get(name)) is not int or result[name] < 0:
                    raise ValueError('Appium result needs nonnegative integer tests, failures, errors and skipped')
            if result['failures'] + result['errors'] + result['skipped'] > result['tests']:
                raise ValueError('Appium counts exceed the number of tests')
            if result['errors'] or process.returncode not in {0, 1}:
                status = 'error'
            elif result['tests'] == result['skipped']:
                status = 'inconclusive'
            elif result['failures']:
                status = 'failed'
            elif process.returncode:
                status = 'error'
            else:
                status = 'passed'
            return {**base, 'status': status, **{k: result[k] for k in ('tests', 'failures', 'errors', 'skipped')}}
        # Legacy k6 summary-export schema: do not treat a process exit alone as proof.
        metrics = result.get('metrics', {})
        checks = metrics.get('checks', {}) if isinstance(metrics, dict) else {}
        passed, failed = checks.get('passes'), checks.get('fails')
        if type(passed) is not int or type(failed) is not int or min(passed, failed) < 0:
            return {**base, 'status': 'inconclusive', 'reason': 'No recognized k6 check counts'}
        threshold_failed = any(value is False for metric in metrics.values() if isinstance(metric, dict)
                               for value in (metric.get('thresholds') or {}).values())
        status = 'error' if process.returncode not in {0, 99} else 'inconclusive' if not passed + failed else 'failed' if failed or threshold_failed or process.returncode == 99 else 'passed'
        return {**base, 'status': status, 'checks_passed': passed, 'checks_failed': failed,
                'threshold_failed': threshold_failed}


def main(argv=None):
    parser = argparse.ArgumentParser(prog='chaosfolk integrations', description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    mail = sub.add_parser('mailpit', help='List or check messages in a test mailbox')
    mail.add_argument('--url', default='http://127.0.0.1:8025')
    mail.add_argument('--message')
    mail.add_argument('--subject')
    mail.add_argument('--recipient')
    mail.add_argument('--contains', action='append', default=[])
    mail.add_argument('--limit', type=int, default=20)
    mail.add_argument('--allow-origin', action='append', default=[])
    file = sub.add_parser('file', help='Check text, CSV or an optional PDF download')
    file.add_argument('path')
    file.add_argument('--kind', choices=['auto', 'csv', 'text', 'pdf'], default='auto')
    file.add_argument('--contains', action='append', default=[])
    file.add_argument('--column', action='append', default=[])
    file.add_argument('--min-rows', type=int)
    file.add_argument('--max-rows', type=int)
    axe = sub.add_parser('axe', help='Run a supplied local axe-core bundle against a test page')
    axe.add_argument('--url', required=True)
    axe.add_argument('--script', required=True)
    axe.add_argument('--allow-origin', action='append', default=[])
    axe.add_argument('--timeout', type=int, default=30)
    external = sub.add_parser('external', help='Run an explicitly configured k6 or Appium test runner')
    external.add_argument('--tool', choices=['k6', 'appium'], required=True)
    external.add_argument('--executable', required=True)
    external.add_argument('--script', required=True)
    external.add_argument('--timeout', type=int, default=120)
    for command in (mail, file, axe, external):
        command.add_argument('--output', help='Write JSON evidence here as well as stdout')
    args = parser.parse_args(argv)
    try:
        if args.command == 'mailpit':
            result = mailpit(args.url, args.message, args.subject, args.contains, args.recipient, args.limit, args.allow_origin)
        elif args.command == 'file':
            result = check_file(args.path, args.kind, args.contains, args.column, args.min_rows, args.max_rows)
        elif args.command == 'axe':
            result = asyncio.run(axe_audit(args.url, args.script, args.allow_origin, args.timeout))
        else:
            result = run_external(args.tool, args.executable, args.script, args.timeout)
    except Exception as error:
        # Browser and parser errors can contain URLs or document content. Do not echo them.
        result = {'adapter': args.command, 'status': 'error', 'error_type': type(error).__name__}
        if isinstance(error, ValueError) and not isinstance(error, (json.JSONDecodeError, UnicodeError)):
            result['reason'] = str(error)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding='utf-8')
    print(encoded)
    return 0 if result['status'] in {'passed', 'listed'} else 1 if result['status'] == 'failed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
