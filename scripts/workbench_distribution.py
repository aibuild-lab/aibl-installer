"""Private immutable setup admission and selected-program bundle acquisition.

The original independently supplied digest is retained outside the workbench.
Installed markers constrain compatibility, but never supply trust admission.
"""
import json
from pathlib import Path
import re
import tempfile

from course_setup import SetupError, command
from frozen_family import acquire, load_distribution
from release_files import atomic, digest, encoded, process_guard, under
from workbench_packages import verify, require_no_pending_sync


def directory(workbench, state_root=None):
    parent=Path(state_root) if state_root else Path.home()/'.aibl/workbench-distributions'
    parent=parent.absolute()
    if any(p.is_symlink() for p in (parent,*parent.parents)):raise SetupError('Linked workbench distribution custody is not supported.')
    root=Path(workbench).resolve()
    if parent==root or parent.is_relative_to(root):raise SetupError('Distribution custody must remain outside the workbench.')
    return under(parent,digest(str(root).encode()))


def read_association(workbench,engine,repository,*,state_root=None,runner=None):
    folder=directory(workbench,state_root)
    path=under(folder,'association.json')
    if not path.is_file():raise SetupError('No retained setup distribution. Obtain the official independently admitted distribution and explicit family inputs; the installed marker cannot supply trust.')
    if path.stat().st_size>16384:raise SetupError('Invalid retained setup association.')
    row=json.loads(path.read_bytes())
    keys={'schema_version','workbench','repository','engine','installer_revision','distribution_sha256','family_sha256','admission'}
    if (not isinstance(row,dict) or set(row)!=keys or row['schema_version']!='aibl.workbench-distribution/v1'
            or row['workbench']!=str(Path(workbench).resolve()) or row['repository']!=repository
            or row['engine']!=str(Path(engine).resolve()) or row['admission']!='independent official setup input'):
        raise SetupError('Retained workbench, repository or engine association differs.')
    value=load_distribution(under(folder,'distribution.json'),row['distribution_sha256'],engine,runner=runner)
    if value['installer']['revision']!=row['installer_revision'] or value['family_sha256']!=row['family_sha256']:
        raise SetupError('Retained distribution association binding differs.')
    return folder,row,value


def retain(workbench,repository,engine,distribution,sha256,*,state_root=None,runner=None):
    """Reserve admission before setup effects; never replace an earlier tuple."""
    folder=directory(workbench,state_root)
    if not re.fullmatch(r'[A-Za-z0-9-]+/[A-Za-z0-9_.-]+',repository):raise SetupError('Verified student repository identity required.')
    value=load_distribution(distribution,sha256,engine,runner=runner)
    if folder.exists():
        _,row,prior=read_association(workbench,engine,repository,state_root=state_root,runner=runner)
        if row['distribution_sha256']!=sha256 or prior!=value:raise SetupError('Setup distribution changed. Resume the original admitted inputs; do not replace the association.')
        return folder,row,value
    if Path(workbench).exists() or Path(workbench).is_symlink():raise SetupError('Existing workbench has no retained setup admission. Obtain the official independent distribution and explicit family inputs.')
    folder.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with process_guard(folder.parent/(folder.name+'.lock')):
        if folder.exists():return retain(workbench,repository,engine,distribution,sha256,state_root=state_root,runner=runner)
        stage=Path(tempfile.mkdtemp(prefix='admission-',dir=folder.parent))
        row={'schema_version':'aibl.workbench-distribution/v1','workbench':str(Path(workbench).resolve()),'repository':repository,'engine':str(Path(engine).resolve()),'installer_revision':value['installer']['revision'],'distribution_sha256':sha256,'family_sha256':value['family_sha256'],'admission':'independent official setup input'}
        atomic(stage/'distribution.json',encoded(value),0o600)
        atomic(stage/'association.json',encoded(row),0o600)
        # Both files become visible together. Abandoned reservations remain diagnostic evidence.
        stage.rename(folder)
    return folder,row,value


def check_cache(folder,value,product):
    cache=under(folder,'bundles')
    package=under(folder,'bundles/'+product)
    if not package.exists():return False
    for name in ('manifest.json','payload.zip'):under(folder,'bundles/'+product+'/'+name)
    verify(cache,product,value['family_lock']['packages'][product])
    return True


def cached_inputs(folder,row,value,engine,products,*,github=None,runner=None):
    """Refresh admission for requested products only, retaining exact bundles."""
    if not products or len(products)!=len(set(products)) or not set(products)<=set(value['family_lock']['packages']):raise SetupError('Choose explicit admitted products.')
    with process_guard(under(folder,'acquisition.lock')):
        missing=[p for p in products if not check_cache(folder,value,p)]
        # Each explicit acquisition rechecks expiry/withdrawal at its admitted index.
        # Installed packages are verified locally by the caller, not redownloaded.
        if products:
            reservation=Path(tempfile.mkdtemp(prefix='acquisition-',dir=folder))
            inputs=acquire(under(folder,'distribution.json'),row['distribution_sha256'],engine,reservation/'verified',products,github=github,runner=runner)
            cache=under(folder,'bundles');cache.mkdir(exist_ok=True,mode=0o700)
            for product in products:
                verify(inputs['family_bundles'],product,value['family_lock']['packages'][product])
                if product in missing:(Path(inputs['family_bundles'])/product).rename(under(folder,'bundles/'+product))
        # Recheck all requested cache bytes and the original admitted engine tuple.
        for product in products:
            if not check_cache(folder,value,product):raise SetupError('Acquired package cache disappeared; preserve the operation for review.')
        load_distribution(under(folder,'distribution.json'),row['distribution_sha256'],engine,runner=runner)
        lock=under(folder,'family-lock.json')
        raw=encoded(value['family_lock'])
        if lock.exists() and lock.read_bytes()!=raw:raise SetupError('Retained family lock changed; preserve it for review.')
        if not lock.exists():atomic(lock,raw,0o600)
    return {'family_lock':str(lock),'family_sha256':value['family_sha256'],'family_bundles':str(under(folder,'bundles'))}


def enrollment_inputs(workbench,product,engine,*,state_root=None,runner=command,engine_runner=None,github=None):
    from enrollment_v2 import identity,installed_record
    if product not in ('agent-workforce','agent-essentials'):raise SetupError('Choose Workforce or the optional lesson-8 support.')
    root=Path(workbench).resolve()
    require_no_pending_sync(root)
    _,repository=identity(root,runner)
    folder,row,value=read_association(root,engine,repository,state_root=state_root,runner=engine_runner)
    current=installed_record(root)
    if current['family']!=value['family_lock'] or any(value['family_lock']['packages'].get(p)!=pin for p,pin in current['packages'].items()):
        raise SetupError('Installed packages differ from the original setup admission. Obtain new independently reviewed update inputs; do not substitute a distribution.')
    # Composition re-verifies installed packages. Reuse their retained exact bundles,
    # never download a different installed package during enrollment.
    for installed in current['packages']:
        if not check_cache(folder,value,installed):raise SetupError('An installed package cache is missing. Recover the original admitted setup artifacts before enrollment.')
    result=cached_inputs(folder,row,value,engine,[product],github=github,runner=engine_runner)
    _,confirmed_repository=identity(root,runner)
    if confirmed_repository!=repository or installed_record(root)!=current:raise SetupError('Workbench identity changed during acquisition. Run preview again.')
    return result
