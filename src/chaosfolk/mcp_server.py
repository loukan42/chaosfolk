"""Read-only MCP stdio access to one explicitly selected Chaosfolk project."""
import argparse
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

from . import __version__
from .campaigns import project_lock

PROTOCOL_VERSION = '2025-06-18'
MAX_FRAME_BYTES = 1024 * 1024
MAX_FILE_BYTES = 4 * 1024 * 1024
LIMIT = 100


def identifier(value):
    value = str(value or '')
    return value if re.fullmatch(r'[a-zA-Z0-9._-]{1,128}', value) else hashlib.sha256(value.encode()).hexdigest()[:16]


def nonnegative(value):
    return value if type(value) is int and value >= 0 else 0


class ProjectReader:
    def __init__(self, directory):
        self.root = Path(directory).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('Project directory must exist')

    def read(self, name, default):
        if name not in {'campaigns.json', 'findings.json'}:
            raise ValueError('File is not exposed')
        path = self.root / name
        if not path.exists():
            return default
        if path.is_symlink() or path.resolve().parent != self.root or not path.is_file():
            raise ValueError('Project data must be regular files inside the selected directory')
        with path.open('rb') as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError('Project file exceeds 4 MiB')
        return json.loads(raw)

    def status(self):
        with project_lock(self.root):
            history = self.read('campaigns.json', {})
            findings = self.read('findings.json', {})
        if not isinstance(history, dict) or not isinstance(findings, dict):
            raise ValueError('Invalid project data')
        campaigns = history.get('campaigns', [])
        if not isinstance(campaigns, list):
            raise ValueError('Invalid campaign history')
        counts = {'open': 0, 'fixed': 0, 'inconclusive': 0, 'other': 0}
        for item in findings.values():
            state = item.get('state') if isinstance(item, dict) else None
            counts[state if state in counts else 'other'] += 1
        latest = campaigns[-1] if campaigns and isinstance(campaigns[-1], dict) else {}
        revision = str(latest.get('revision') or '')
        return {'campaigns': len(campaigns), 'findings': len(findings), 'states': counts,
                'latest_revision': revision if re.fullmatch(r'[a-f0-9]{7,40}', revision) else None,
                'scope': 'Metadata only; no browser, authentication state, titles or scenario payloads are exposed.'}

    def findings(self, offset=0, limit=20):
        with project_lock(self.root):
            findings = self.read('findings.json', {})
        if not isinstance(findings, dict):
            raise ValueError('Invalid findings registry')
        result = []
        for key, item in islice(findings.items(), offset, offset + limit):
            if not isinstance(item, dict):
                continue
            state = item.get('state')
            severity = item.get('severity')
            result.append({'fingerprint': identifier(key),
                           'state': state if state in {'open', 'fixed', 'inconclusive'} else 'unknown',
                           'severity': severity if severity in {'blocking', 'annoying', 'minor', 'bloquant', 'genant', 'gênant', 'mineur'} else 'unknown',
                           'occurrences': nonnegative(item.get('seen')),
                           'assertions': nonnegative(item.get('assertions'))})
        return {'findings': result, 'total': len(findings), 'offset': offset,
                'next_offset': offset + limit if offset + limit < len(findings) else None}

    def scenarios(self, offset=0, limit=20):
        with project_lock(self.root):
            return self._scenarios(offset, limit)

    def _scenarios(self, offset, limit):
        folder = self.root / 'scenarios'
        if not folder.exists():
            return {'scenarios': [], 'total': 0, 'offset': offset, 'next_offset': None}
        if folder.is_symlink() or folder.resolve().parent != self.root or not folder.is_dir():
            raise ValueError('Scenario directory must be inside the selected project')
        # Return names only. Raw scenarios contain authentication and typed input.
        names = []
        resolved = folder.resolve()
        with os.scandir(folder) as entries:
            for count, entry in enumerate(entries, 1):
                if count > 10000:
                    raise ValueError('Scenario directory exceeds the listing limit')
                file = Path(entry.path)
                if (file.suffix == '.json' and entry.is_file(follow_symlinks=False)
                        and file.resolve().parent == resolved):
                    names.append(identifier(file.stem))
        names.sort()
        return {'scenarios': names[offset:offset + limit], 'total': len(names), 'offset': offset,
                'next_offset': offset + limit if offset + limit < len(names) else None}


def tools_list():
    pagination = {'type': 'object', 'properties': {
        'offset': {'type': 'integer', 'minimum': 0, 'maximum': 100000, 'default': 0},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': LIMIT, 'default': 20}}, 'additionalProperties': False}
    return [{'name': name, 'description': description, 'inputSchema': schema,
             'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False}}
            for name, description, schema in [
                ('campaign_status', 'Counts and latest revision for the configured project. No filesystem paths or content.',
                 {'type': 'object', 'properties': {}, 'additionalProperties': False}),
                ('list_findings', 'Finding fingerprints, severity, state and recurrence. Titles and raw evidence remain private.', pagination),
                ('list_scenarios', 'Names of saved scenarios. No scenario bodies, cookies or typed values.', pagination)]]


class Server:
    def __init__(self, directory):
        self.reader = ProjectReader(directory)
        self.initialized = False

    def handle(self, request):
        def error(code, message, request_id=None):
            return {'jsonrpc': '2.0', 'id': request_id, 'error': {'code': code, 'message': message}}
        if not isinstance(request, dict) or request.get('jsonrpc') != '2.0' or not isinstance(request.get('method'), str):
            return error(-32600, 'Invalid Request')
        request_id = request.get('id')
        if 'id' in request and (request_id is None or type(request_id) not in {str, int}):
            return error(-32600, 'Invalid request id')
        method = request['method']
        params = request.get('params', {})
        if 'id' not in request:
            # No responses to notifications, including unknown extensions.
            return None
        if not isinstance(params, dict):
            return error(-32602, 'Parameters must be an object', request_id)
        if method == 'initialize':
            result = {'protocolVersion': PROTOCOL_VERSION, 'capabilities': {'tools': {}},
                      'serverInfo': {'name': 'chaosfolk', 'version': __version__},
                      'instructions': 'Read-only project metadata. Use the CLI for browser execution or full evidence.'}
            self.initialized = True
        elif method == 'ping':
            result = {}
        elif not self.initialized:
            return error(-32000, 'Initialize the server first', request_id)
        elif method == 'tools/list':
            result = {'tools': tools_list()}
        elif method == 'tools/call':
            name, arguments = params.get('name'), params.get('arguments', {})
            if not isinstance(arguments, dict):
                return error(-32602, 'Tool arguments must be an object', request_id)
            if not isinstance(name, str) or name not in {'campaign_status', 'list_findings', 'list_scenarios'}:
                return error(-32602, 'Unknown tool', request_id)
            permitted = set() if name == 'campaign_status' else {'offset', 'limit'}
            if set(arguments) - permitted:
                return error(-32602, 'Unknown tool argument', request_id)
            offset, limit = arguments.get('offset', 0), arguments.get('limit', 20)
            if type(offset) is not int or not 0 <= offset <= 100000 or type(limit) is not int or not 1 <= limit <= LIMIT:
                return error(-32602, 'Invalid pagination', request_id)
            try:
                if name == 'campaign_status':
                    data = self.reader.status()
                elif name == 'list_findings':
                    data = self.reader.findings(offset, limit)
                else:
                    data = self.reader.scenarios(offset, limit)
                result = {'content': [{'type': 'text', 'text': json.dumps(data, ensure_ascii=False)}],
                          'structuredContent': data, 'isError': False}
            except (OSError, ValueError, TypeError, RecursionError, sqlite3.Error):
                result = {'content': [{'type': 'text', 'text': 'Cannot read the configured project metadata.'}], 'isError': True}
        else:
            return error(-32601, 'Method not found', request_id)
        return {'jsonrpc': '2.0', 'id': request_id, 'result': result}


def serve(directory, input_stream, output_stream):
    server = Server(directory)
    while True:
        raw = input_stream.readline(MAX_FRAME_BYTES + 1)
        if not raw:
            return 0
        if len(raw) > MAX_FRAME_BYTES:
            return 2
        try:
            request = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
            response = server.handle(request)
        except (ValueError, UnicodeError, RecursionError):
            response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=True) + '\n')
            output_stream.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(prog='chaosfolk mcp', description=__doc__)
    parser.add_argument('--project-dir', required=True, help='One existing project memory folder to expose')
    args = parser.parse_args(argv)
    try:
        return serve(args.project_dir, sys.stdin.buffer, sys.stdout)
    except (OSError, ValueError):
        print('Cannot open the selected project directory.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
