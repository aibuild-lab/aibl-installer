"""Bounded read-only GitHub release asset transport for admitted identities."""
import json
import re
import subprocess
import threading
from urllib.parse import quote
from workbench_packages import ReleaseError

INSTALLER = 'aibuild-lab/aibl-installer'
REPOSITORIES = {INSTALLER, 'aibuild-lab/my-workbench-template', 'aibuild-lab/agent-workforce'}


def validate_locator(value):
    if not isinstance(value, dict) or set(value) != {'repository', 'release_tag', 'release_target'}:
        raise ReleaseError('GitHub release locator contract')
    if value['repository'] not in REPOSITORIES:
        raise ReleaseError('GitHub repository is not admitted')
    if not isinstance(value['release_tag'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value['release_tag']):
        raise ReleaseError('Invalid exact release tag')
    if not isinstance(value['release_target'], str) or not re.fullmatch('[a-f0-9]{40}', value['release_target']):
        raise ReleaseError('Exact release target required')
    return value


class GitHubAssets:
    def __init__(self, transport=None):
        self.transport = transport or self._gh

    @staticmethod
    def _gh(args, limit):
        with subprocess.Popen(['gh', 'api', '--hostname', 'github.com', '--method', 'GET', *args],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
            timer = threading.Timer(30, process.kill)
            timer.start()
            try:
                raw = process.stdout.read(limit + 1)
                if len(raw) > limit:
                    process.kill()
                    raise ReleaseError('GitHub response exceeds size limit')
                if process.wait(timeout=5) != 0:
                    raise ReleaseError('GitHub release access failed; inspect account access or connection')
                return raw
            finally:
                timer.cancel()

    def _read(self, args, limit):
        raw = self.transport(args, limit)
        if not isinstance(raw, bytes) or len(raw) > limit:
            raise ReleaseError('GitHub response exceeds size limit')
        return raw

    def _json(self, route):
        return json.loads(self._read([route], 2 * 1024 * 1024))

    def release(self, locator):
        locator = validate_locator(locator)
        repo, tag = locator['repository'], locator['release_tag']
        release = self._json(f'repos/{repo}/releases/tags/{quote(tag, safe="")}')
        if not isinstance(release, dict) or release.get('tag_name') != tag or release.get('draft') is not False:
            raise ReleaseError('Wrong tag or draft release')
        ident = release.get('id')
        if type(ident) is not int or ident <= 0 or release.get('url') != f'https://api.github.com/repos/{repo}/releases/{ident}':
            raise ReleaseError('Release repository identity mismatch')
        ref = self._json(f'repos/{repo}/git/ref/tags/{quote(tag, safe="")}')
        if ref.get('ref') != 'refs/tags/' + tag:
            raise ReleaseError('Release tag reference mismatch')
        obj = ref.get('object', {})
        for _ in range(5):
            sha = obj.get('sha')
            if not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{40}', sha):
                raise ReleaseError('Invalid tag object identity')
            if obj.get('type') == 'commit':
                if sha != locator['release_target']:
                    raise ReleaseError('Release target differs from admission')
                return repo, ident
            if obj.get('type') != 'tag':
                raise ReleaseError('Unsupported release tag object')
            annotated = self._json(f'repos/{repo}/git/tags/{sha}')
            if annotated.get('sha') != sha:
                raise ReleaseError('Annotated tag identity mismatch')
            obj = annotated.get('object', {})
        raise ReleaseError('Release tag nesting exceeds limit')

    def fetch(self, locator, name, limit):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', name):
            raise ReleaseError('Invalid admitted asset name')
        repo, ident = self.release(locator)
        rows = []
        for page in range(1, 11):
            batch = self._json(f'repos/{repo}/releases/{ident}/assets?per_page=100&page={page}')
            if not isinstance(batch, list):
                raise ReleaseError('Invalid asset listing')
            rows.extend(batch)
            if len(batch) < 100:
                break
        else:
            raise ReleaseError('Release asset inventory exceeds limit')
        hits = [row for row in rows if isinstance(row, dict) and row.get('name') == name]
        if len(hits) != 1:
            raise ReleaseError('Release asset missing or ambiguous')
        asset = hits[0]
        aid, size = asset.get('id'), asset.get('size')
        if type(aid) is not int or aid <= 0 or type(size) is not int or not 0 <= size <= limit:
            raise ReleaseError('Invalid or oversized asset identity')
        route = f'repos/{repo}/releases/assets/{aid}'
        if asset.get('url') != 'https://api.github.com/' + route or asset.get('state') != 'uploaded':
            raise ReleaseError('Asset repository identity mismatch')
        raw = self._read(['-H', 'Accept: application/octet-stream', route], limit)
        if len(raw) != size:
            raise ReleaseError('Asset size changed during download')
        return raw
