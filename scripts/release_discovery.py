"""Read-only discovery using an independently admitted exact index digest.

No trust provisioning, private-account bypass, scheduling or automatic apply.
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import tempfile
import zipfile
import urllib.parse
import urllib.request
from pathlib import Path
from workbench_packages import PRODUCTS, MAX_BYTES, ReleaseError, digest, verify, version_key, validate_pin
from release_files import encoded
from github_assets import GitHubAssets, validate_locator, INSTALLER

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ReleaseError('Redirect requires separate admission')

def origin(url):
    p=urllib.parse.urlsplit(url)
    if p.username or p.password or p.query or p.fragment:
        raise ReleaseError('URL credentials, query and fragment forbidden')
    if p.scheme=='file' and not p.netloc:return 'file://'
    if p.scheme!='https' or not p.hostname:raise ReleaseError('HTTPS required')
    return 'https://'+p.netloc

def fetch(url, admitted_origin, local_simulation, limit):
    if origin(url)!=admitted_origin or (admitted_origin=='file://' and not local_simulation):
        raise ReleaseError('Unadmitted transport')
    with urllib.request.build_opener(NoRedirect).open(url,timeout=20) as response:
        raw=response.read(limit+1)
    if len(raw)>limit:raise ReleaseError('Response exceeds size limit')
    return raw

def instant(value):
    if not isinstance(value,str) or not value.endswith('Z'):raise ReleaseError('UTC timestamp required')
    result=dt.datetime.fromisoformat(value[:-1]+'+00:00')
    if result.utcoffset()!=dt.timedelta(0):raise ReleaseError('UTC timestamp required')
    return result

def validate_trust(trust, descriptor_sha256):
    if not isinstance(trust,dict) or set(trust)!={'schema_version','product','index_release','index_asset','index_sha256','minimum_sequence'} or trust['schema_version']!='aibl.release-trust/v2':raise ReleaseError('Trust v2 contract')
    if not isinstance(descriptor_sha256,str) or not re.fullmatch('[a-f0-9]{64}',descriptor_sha256) or digest(encoded(trust))!=descriptor_sha256:raise ReleaseError('Independent descriptor digest mismatch')
    if trust['product'] not in PRODUCTS or type(trust['minimum_sequence']) is not int or trust['minimum_sequence']<1:raise ReleaseError('Trust identity')
    if not isinstance(trust['index_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',trust['index_sha256']):raise ReleaseError('Trust index digest')
    validate_locator(trust['index_release'])
    if trust['index_release']['repository']!=INSTALLER or trust['index_asset']!='index-'+trust['product']+'.json':raise ReleaseError('Index asset is not admitted')
    return trust

def acquire_v2(trust, descriptor_sha256, installer_revision, destination, *, expected_pin=None, github=None, now=None):
    """Download into a new product directory after independent descriptor admission.

    Returns a verified candidate, never applies files or activates an app. A failed
    partial download is preserved in the caller's external destination for review.
    """
    validate_trust(trust,descriptor_sha256)
    github=github or GitHubAssets()
    raw=github.fetch(trust['index_release'],trust['index_asset'],65536)
    if digest(raw)!=trust['index_sha256']:raise ReleaseError('Index integrity mismatch')
    index=json.loads(raw)
    if not isinstance(index,dict) or set(index)!={'schema_version','product','sequence','generated_at','expires_at','package','installer_revision','withdrawn'} or index['schema_version']!='aibl.release-index/v2':raise ReleaseError('Index v2 contract')
    if index['product']!=trust['product'] or type(index['sequence']) is not int or index['sequence']<trust['minimum_sequence']:raise ReleaseError('Wrong product or obsolete index')
    clock=now or dt.datetime.now(dt.timezone.utc)
    if not instant(index['generated_at'])<=clock<instant(index['expires_at']):raise ReleaseError('Index expired or not yet valid')
    if not isinstance(installer_revision,str) or not re.fullmatch('[a-f0-9]{40}',installer_revision) or index['installer_revision']!=installer_revision or trust['index_release']['release_target']!=installer_revision:raise ReleaseError('Incompatible installer revision')
    if not isinstance(index['withdrawn'],bool):raise ReleaseError('Withdrawal contract')
    pin=index['package'];validate_pin(index['product'],pin,True)
    if expected_pin is not None and pin!=expected_pin:raise ReleaseError('Discovery differs from admitted family lock')
    if index['withdrawn']:return {'update_availability':'withdrawn','sequence':index['sequence'],'package':pin}
    locator={'repository':pin['publisher'],'release_tag':pin['release_tag'],'release_target':pin['release_target']}
    destination=Path(destination).absolute()
    if any(p.is_symlink() for p in (destination,*destination.parents)):raise ReleaseError('Bundle destination is linked')
    folder=destination/index['product']
    if folder.exists():raise ReleaseError('Preserve existing bundle; choose a new destination')
    folder.mkdir(parents=True,mode=0o700)
    for name,field,limit in [('manifest.json','manifest_sha256',2*1024*1024),('payload.zip','archive_sha256',MAX_BYTES)]:
        data=github.fetch(locator,name,limit)
        if digest(data)!=pin[field]:raise ReleaseError('Package asset integrity mismatch')
        with (folder/name).open('xb') as stream:stream.write(data)
    verify(destination,index['product'],pin)
    return {'update_availability':'verified_candidate','sequence':index['sequence'],'package':pin,'bundle':str(folder),'active_use':'unverified'}

def discover(trust, installer_revision, *, local_simulation=False, now=None, descriptor_sha256=None, github=None):
    """Never changes the workbench. Temporary verified bundles are discarded."""
    try:
        if isinstance(trust,dict) and trust.get('schema_version')=='aibl.release-trust/v2':
            with tempfile.TemporaryDirectory(prefix='aibl-discovery-') as directory:
                result=acquire_v2(trust,descriptor_sha256,installer_revision,Path(directory).resolve(),github=github,now=now)
                result.pop('bundle',None)
                return result
        if set(trust)!={'schema_version','product','index_url','index_sha256','allowed_origin','minimum_sequence'} or trust['schema_version']!='aibl.release-trust/v1':raise ReleaseError('Trust contract')
        if trust['product'] not in PRODUCTS or type(trust['minimum_sequence']) is not int or trust['minimum_sequence']<1:raise ReleaseError('Trust identity')
        if not re.fullmatch('[0-9a-f]{64}',trust['index_sha256']):raise ReleaseError('Trust digest')
        raw=fetch(trust['index_url'],trust['allowed_origin'],local_simulation,65536)
        if digest(raw)!=trust['index_sha256']:raise ReleaseError('Index integrity mismatch')
        index=json.loads(raw)
        if set(index)!={'schema_version','product','sequence','generated_at','expires_at','package','installer_revision','withdrawn','package_url'} or index['schema_version']!='aibl.release-index/v1':raise ReleaseError('Index contract')
        if index['product']!=trust['product'] or type(index['sequence']) is not int or index['sequence']<trust['minimum_sequence']:raise ReleaseError('Wrong product or obsolete index')
        clock=now or dt.datetime.now(dt.timezone.utc)
        if not instant(index['generated_at'])<=clock<instant(index['expires_at']):raise ReleaseError('Index expired or not yet valid')
        if not isinstance(index['withdrawn'],bool):raise ReleaseError('Withdrawal contract')
        if not re.fullmatch('[0-9a-f]{40}',index['installer_revision']):raise ReleaseError('Installer identity contract')
        if index['installer_revision']!=installer_revision:raise ReleaseError('Incompatible installer revision')
        pin=index['package']
        if set(pin)!={'version','manifest_sha256','archive_sha256','publisher'} or pin['publisher']!='aibuild-lab/'+index['product']:raise ReleaseError('Package pin contract')
        if any(not re.fullmatch('[0-9a-f]{64}',pin[k]) for k in ('manifest_sha256','archive_sha256')):raise ReleaseError('Package digest contract')
        version_key(pin['version'])
        if index['withdrawn']:return {'update_availability':'withdrawn','sequence':index['sequence'],'package':pin}
        with tempfile.TemporaryDirectory(prefix='aibl-discovery-') as directory:
            folder=Path(directory)/index['product'];folder.mkdir()
            for name,limit in [('manifest.json',2*1024*1024),('payload.zip',MAX_BYTES)]:
                (folder/name).write_bytes(fetch(index['package_url'].rstrip('/')+'/'+name,trust['allowed_origin'],local_simulation,limit))
            verify(directory,index['product'],pin)
        return {'update_availability':'verified_candidate','sequence':index['sequence'],'package':pin,'package_url':index['package_url'],'active_use':'unverified'}
    except (ValueError,TypeError,KeyError,OSError,AttributeError,RuntimeError,zipfile.BadZipFile,subprocess.SubprocessError) as error:
        return {'update_availability':'unknown','reason':str(error)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trust',required=True);p.add_argument('--installer-revision',required=True);p.add_argument('--local-simulation',action='store_true');p.add_argument('--descriptor-sha256')
    a=p.parse_args();raw=Path(a.trust).read_bytes();trust=json.loads(raw)
    if trust.get('schema_version')=='aibl.release-trust/v2' and raw!=encoded(trust):raise ReleaseError('Trust descriptor must use the reviewed canonical encoding')
    print(json.dumps(discover(trust,a.installer_revision,local_simulation=a.local_simulation,descriptor_sha256=a.descriptor_sha256)))
if __name__=='__main__':main()
