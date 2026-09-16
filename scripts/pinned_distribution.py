"""Verify an attended immutable course distribution and seed an independent workbench.

The reviewed lock and its digest arrive outside the downloaded release. This
module contains no private course payload, credentials, or default release pin.
"""
from __future__ import annotations
import hashlib, io, json, os, re, stat, tempfile, uuid, zipfile
from pathlib import Path, PurePosixPath

INSTALLER_FILES = ('start.sh', 'start.ps1', 'course-options.json', 'scripts/course_setup.py', 'scripts/pinned_distribution.py', 'SETUP-PROMPT.md', 'scripts/enroll.py')
PRODUCTS = ('agent-essentials', 'agent-native-workforce')
MAX_BYTES = 16 * 1024 * 1024

def require(ok, message):
    if not ok: raise ValueError(message)

def digest(data): return hashlib.sha256(data).hexdigest()
def encoded(data): return (json.dumps(data, sort_keys=True, indent=2) + '\n').encode('utf-8')
def exact(value, keys, label): require(isinstance(value, dict) and set(value) == set(keys), label + ' has unexpected or missing fields.')

def validate_pin(pin, product):
    exact(pin, ('schema_version', 'product', 'release_id', 'source_revision', 'archive_sha256', 'manifest_sha256'), 'Release pin')
    require(pin['schema_version'] == 'aibl.release-pin/v3' and pin['product'] == product, 'Wrong product pin.')
    require(isinstance(pin['release_id'], str) and re.fullmatch(re.escape(product) + r'-v\d+\.\d+\.\d+(?:-[a-z0-9]+(?:[.-][a-z0-9]+)*)?', pin['release_id']), 'Release ID is not immutable.')
    require(re.fullmatch('[a-f0-9]{40}', pin['source_revision'] or '') is not None, 'Invalid source revision.')
    require(all(re.fullmatch('[a-f0-9]{64}', pin[key] or '') for key in ('archive_sha256', 'manifest_sha256')), 'Invalid release digests.')

def validate_lock(value):
    exact(value, ('schema_version', 'course_id', 'installer', 'source_release_pins'), 'Distribution lock')
    # course_id is the registry program id; the source_release_pins keys below stay the release tool's product ids.
    require(value['schema_version'] == 'aibl.course-distribution/v1' and value['course_id'] == 'agent-workforce', 'Unsupported pinned course.')
    exact(value['installer'], ('repository', 'commit', 'files'), 'Installer pin')
    require(value['installer']['repository'] == 'aibuild-lab/aibl-installer' and re.fullmatch('[a-f0-9]{40}', value['installer']['commit'] or ''), 'Wrong installer identity.')
    exact(value['installer']['files'], INSTALLER_FILES, 'Installer file inventory')
    require(all(re.fullmatch('[a-f0-9]{64}', sha or '') for sha in value['installer']['files'].values()), 'Invalid installer file hash.')
    exact(value['source_release_pins'], PRODUCTS, 'Course product pins')
    for product in PRODUCTS: validate_pin(value['source_release_pins'][product], product)
    require(len({value['source_release_pins'][p]['source_revision'] for p in PRODUCTS}) == 1, 'Product pins come from different accepted sources.')
    return value

def load_lock(path, expected_sha256, installer_root, runner, bootstrap_path=None):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 65536, 'Choose the reviewed distribution lock file.')
    data = path.read_bytes()
    require(re.fullmatch('[a-f0-9]{64}', expected_sha256 or '') and digest(data) == expected_sha256, 'Distribution lock does not match its independently supplied digest.')
    value = validate_lock(json.loads(data))
    require(runner(['git', 'rev-parse', 'HEAD'], cwd=installer_root) == value['installer']['commit'], 'Installer revision differs from the reviewed distribution.')
    require(not runner(['git', 'status', '--porcelain'], cwd=installer_root), 'Pinned installer checkout has local changes; use the frozen launcher again.')
    for name, sha in value['installer']['files'].items():
        target = Path(installer_root) / name
        require(target.is_file() and not target.is_symlink() and digest(target.read_bytes()) == sha, 'Installer file differs from the reviewed distribution: ' + name)
    if bootstrap_path:
        bootstrap = Path(bootstrap_path)
        require(bootstrap.name in ('start.sh', 'start.ps1') and bootstrap.is_file() and digest(bootstrap.read_bytes()) == value['installer']['files'][bootstrap.name], 'Executed platform launcher differs from the pinned bytes.')
    return value, digest(data)

def safe_name(name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name and '\0' not in name, 'Unsafe payload path.')
    path = PurePosixPath(name)
    require(not path.is_absolute() and path.as_posix() == name and all(part.casefold() not in ('.', '..', '.git', '.aibl-local') and not part.endswith((' ', '.')) and not re.match(r'(?i)^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)', part) for part in path.parts), 'Unsafe payload destination.')
    require(name not in ('.aibl/distribution.json', '.aibl/installed-agent-essentials.json'), 'Payload collides with installer provenance.')
    return name

def verify_bundle(bundle, pin, product='agent-essentials'):
    validate_pin(pin, product)
    bundle = Path(bundle)
    require(not bundle.is_symlink(), 'Bundle root must not be a symlink.')
    for name in ('manifest.json', 'payload.zip'):
        p = bundle / name
        require(p.is_file() and not p.is_symlink() and p.stat().st_size <= MAX_BYTES, 'Invalid or oversized release input.')
    manifest_bytes = (bundle / 'manifest.json').read_bytes(); archive = (bundle / 'payload.zip').read_bytes()
    require(digest(manifest_bytes) == pin['manifest_sha256'] and digest(archive) == pin['archive_sha256'], 'Private release bytes do not match reviewed pins.')
    manifest = json.loads(manifest_bytes)
    exact(manifest, ('schema_version', 'product', 'release_id', 'source_repository', 'source_revision', 'files'), 'Release manifest')
    require(encoded(manifest) == manifest_bytes, 'Release manifest must use the canonical v3 encoding.')
    require(manifest['schema_version'] == 'aibl.course-release/v3' and manifest['source_repository'] == 'aibuild-lab/agent-native-workforce-internal', 'Wrong release source.')
    require(all(manifest[key] == pin[key] for key in ('product', 'release_id', 'source_revision')), 'Release identity differs from its reviewed pin.')
    require(isinstance(manifest['files'], list) and 0 < len(manifest['files']) <= 2000, 'Invalid release file inventory.')
    entries = {}; folded = set(); sources = set()
    for entry in manifest['files']:
        exact(entry, ('source', 'path', 'sha256', 'mode'), 'Release file'); safe_name(entry['path']); safe_name(entry['source'])
        require(entry['path'].casefold() not in folded and entry['source'] not in sources and entry['mode'] in (0o644, 0o755) and re.fullmatch('[a-f0-9]{64}', entry['sha256'] or ''), 'Duplicate or invalid release file.')
        entries[entry['path']] = entry; folded.add(entry['path'].casefold()); sources.add(entry['source'])
    payload = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as archive_file:
        members = archive_file.infolist()
        require(len(members) == len(entries) and {m.filename for m in members} == set(entries) and sum(m.file_size for m in members) <= MAX_BYTES, 'Undeclared, duplicate or oversized archive member.')
        for member in members:
            mode = member.external_attr >> 16
            require(not member.is_dir() and not member.flag_bits & 1 and stat.S_IFMT(mode) in (0, stat.S_IFREG), 'Archive contains a nonregular member.')
            data = archive_file.read(member)
            require(digest(data) == entries[member.filename]['sha256'], 'Archive file differs from manifest.')
            payload[member.filename] = data
    if product == 'agent-essentials':require('scripts/aibl.py' in payload, 'Essentials setup helper is missing.')
    return manifest, payload

def local_input(value, directory=False):
    path=Path(value).expanduser().absolute()
    require('..' not in path.parts and not any(p.is_symlink() for p in [path,*path.parents]), 'Candidate input has a linked or traversal path.')
    require(path.is_dir() if directory else path.is_file(), 'Candidate input is missing. Supply its explicit local path; no release fallback is used.')
    return path

def preview_bundle(directory, distribution):
    """Verify both local products against independently supplied frozen pins."""
    validate_lock(distribution);directory=local_input(directory,True);products={}
    for product in PRODUCTS:
        folder=local_input(directory/product,True)
        for name in ('manifest.json','payload.zip'):local_input(folder/name)
        products[product]=verify_bundle(folder,distribution['source_release_pins'][product],product)
    return products

def record_candidate_transport(folder, directory, lock_path, distribution, distribution_sha256, rehearsal_id=None):
    folder=Path(folder).resolve();directory=local_input(directory,True);lock_path=local_input(lock_path)
    provenance=folder/'.aibl/distribution.json'
    require(not provenance.parent.is_symlink() and not provenance.is_symlink() and provenance.is_file(), 'Installed candidate provenance is missing or linked; preserve the project.')
    installed=json.loads(provenance.read_bytes())
    require(isinstance(installed,dict) and installed.get('delivery_mode')=='local_candidate'
            and installed.get('distribution_sha256')==distribution_sha256
            and installed.get('source_release_pins')==distribution['source_release_pins']
            and installed.get('installer_commit')==distribution['installer']['commit'],
            'This installed project is not the matching local candidate. Use a fresh project; published provenance is never converted.')
    lock_bytes=lock_path.read_bytes()
    require(digest(lock_bytes)==distribution_sha256, 'Candidate lock changed before transport was recorded.')
    require(json.loads(lock_bytes)==distribution, 'Candidate distribution changed before transport was recorded.')
    preview_bundle(directory,distribution)
    local=folder/'.aibl-local';require(not local.is_symlink(), 'Candidate local state cannot be a symlink.');local.mkdir(exist_ok=True)
    record={'schema_version':'aibl.candidate-transport/v1','project_root':str(folder),
            'bundle_root':str(directory),'distribution_lock':str(lock_path),
            'distribution_sha256':distribution_sha256,
            'source_revision':distribution['source_release_pins']['agent-essentials']['source_revision']}
    marker={'schema_version':'aibl.rehearsal-project/v1','rehearsal_id':rehearsal_id,'actor':'automated_test','course_credit':False}
    files={'candidate-distribution.json':record}
    if rehearsal_id:files['rehearsal.json']=marker
    for name,value in files.items():
        path=local/name;require(not path.is_symlink(), 'Candidate local record cannot be a symlink.')
        if path.exists():require(json.loads(path.read_bytes())==value, 'Candidate local transport differs. Explicitly relink and verify it before resuming.')
        else:
            with path.open('xb') as stream:stream.write(encoded(value))
            path.chmod(0o600)

def download_bundle(distribution, directory, runner):
    pin = distribution['source_release_pins']['agent-essentials']
    runner(['gh', 'release', 'download', pin['release_id'], '--repo', 'aibuild-lab/agent-essentials', '--pattern', 'manifest.json', '--pattern', 'payload.zip', '--dir', str(directory)])
    return verify_bundle(directory, pin)

def ensure_private_repository(full, existing, state, distribution_sha256, runner, save):
    intent = state.get('pinned_creation_intent')
    if existing:
        require(existing.get('private') is True and existing.get('full_name', '').lower() == full.lower(), 'Existing repository is not the expected private destination.')
        known_id = state.get('created_repository_id') == existing.get('id') and existing.get('id') is not None
        own_intent = intent and intent.get('repository') == full and intent.get('distribution_sha256') == distribution_sha256 and existing.get('description') == intent.get('description')
        require(known_id or own_intent, 'Repository name collision. Existing work is preserved; choose a new project name.')
        return
    if not intent:
        intent = {'repository': full, 'distribution_sha256': distribution_sha256, 'description': 'AIBL private workbench setup ' + uuid.uuid4().hex}
        state['pinned_creation_intent'] = intent; save()
    require(intent['repository'] == full and intent['distribution_sha256'] == distribution_sha256, 'Saved creation intent belongs to another distribution.')
    runner(['gh', 'repo', 'create', full, '--private', '--description', intent['description']])

def seed_project(folder, temporary, full, manifest, payload, distribution, distribution_sha256, user, runner, local_candidate=False):
    """Resume only the installer's staging folder. Never rewrite a student's project."""
    folder = Path(folder); temporary = Path(temporary)
    require(not folder.exists() and not temporary.is_symlink(), 'Pinned setup destination is occupied or linked. Preserve it for review.')
    temporary.mkdir(parents=True, exist_ok=True)
    require(not (temporary / '.git').is_symlink() and (not (temporary / '.git').exists() or (temporary / '.git').is_dir()), 'Staging Git metadata is linked or unexpected. It is preserved.')
    if not (temporary / '.git').exists():
        require(not any(temporary.iterdir()), 'Interrupted setup contains unrecognized work. It is preserved.')
        runner(['git', 'init', '--initial-branch=main'], cwd=temporary)
        runner(['git', 'remote', 'add', 'origin', 'https://github.com/' + full + '.git'], cwd=temporary)
    require(runner(['git', 'config', '--local', '--get', 'remote.origin.url'], cwd=temporary) in ('https://github.com/' + full + '.git', 'https://github.com/' + full), 'Staging origin differs from the private destination.')
    require(Path(runner(['git', 'rev-parse', '--show-toplevel'], cwd=temporary)).resolve() == temporary.resolve(), 'Staging is not the project root.')
    files = dict(payload)
    files['.aibl/installed-agent-essentials.json'] = encoded(manifest)
    files['.aibl/distribution.json'] = encoded({'schema_version': 'aibl.installed-distribution/v1', 'distribution_sha256': distribution_sha256, 'installer_commit': distribution['installer']['commit'], 'source_release_pins': distribution['source_release_pins'], 'workforce_adoption': 'pending Essentials gate'})
    if local_candidate:
        record=json.loads(files['.aibl/distribution.json']);record['delivery_mode']='local_candidate';files['.aibl/distribution.json']=encoded(record)
    # Walk before writing; reject symlinks and preserve every unexpected file.
    for path in temporary.rglob('*'):
        rel = path.relative_to(temporary).as_posix()
        if rel == '.git' or rel.startswith('.git/'): continue
        require(not path.is_symlink(), 'Staging contains a symlink; no files were changed.')
        require(path.is_dir() or path.is_file(), 'Staging contains a nonregular file; no files were changed.')
        if path.is_file(): require(rel in files and path.read_bytes() == files[rel], 'Staging contains changed or unrecognized work; it is preserved.')
    for name, data in files.items():
        path = temporary / name; path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open('xb') as stream: stream.write(data)
        if name in payload: path.chmod(next(e['mode'] for e in manifest['files'] if e['path'] == name))
    runner(['git', 'config', '--local', 'user.name', user.get('name') or user['login']], cwd=temporary)
    runner(['git', 'config', '--local', 'user.email', str(user['id']) + '+' + user['login'] + '@users.noreply.github.com'], cwd=temporary)
    try: head = runner(['git', 'rev-parse', '--verify', 'HEAD'], cwd=temporary)
    except ValueError: head = ''
    if not head:
        runner(['git', 'add', '--force', '--', *sorted(files)], cwd=temporary)
        runner(['git', 'commit', '-m', 'Start private workbench from ' + manifest['release_id']], cwd=temporary)
        head = runner(['git', 'rev-parse', 'HEAD'], cwd=temporary)
    require(not runner(['git', 'status', '--porcelain'], cwd=temporary), 'Staging has unfinished changes. Preserve it for review.')
    require(runner(['git', 'rev-list', '--count', 'HEAD'], cwd=temporary) == '1', 'Pinned template must begin an independent single-root history.')
    remote = runner(['git', 'ls-remote', '--heads', 'origin'], cwd=temporary)
    if remote:
        require(remote.split() == [head, 'refs/heads/main'], 'Private remote changed during setup. Both copies are preserved.')
    else:
        runner(['git', 'push', '--set-upstream', 'origin', 'HEAD:refs/heads/main'], cwd=temporary)
        require(runner(['git', 'ls-remote', '--heads', 'origin'], cwd=temporary).split() == [head, 'refs/heads/main'], 'Initial private push was not verified. Rerun the same setup.')
    require(not folder.exists(), 'Project destination appeared during setup. Preserve both folders.')
    temporary.rename(folder)

def verify_installed_helper(folder, distribution, distribution_sha256):
    folder = Path(folder); record = folder / '.aibl/distribution.json'; manifest_path = folder / '.aibl/installed-agent-essentials.json'
    require(not record.is_symlink() and not manifest_path.is_symlink() and not (folder / '.aibl').is_symlink(), 'Installed provenance must not be a symlink.')
    value = json.loads(record.read_text(encoding='utf-8'))
    require(value.get('distribution_sha256') == distribution_sha256 and value.get('source_release_pins') == distribution['source_release_pins'], 'Project belongs to another frozen distribution. Use the supported update path; no files were changed.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    require(digest(encoded(manifest)) == distribution['source_release_pins']['agent-essentials']['manifest_sha256'], 'Installed Essentials manifest differs from the pinned release.')
    for entry in manifest['files']:
        if entry['path'].startswith('scripts/'):
            target = folder / entry['path']
            require(not target.is_symlink() and not (folder / 'scripts').is_symlink() and target.is_file() and digest(target.read_bytes()) == entry['sha256'], 'Installed helper changed. Preserve it and use the supported update or repair path.')
