"""Read-only discovery using an independently admitted exact index digest.

No trust provisioning, private-account bypass, scheduling or automatic apply.
"""
import argparse
import datetime as dt
import json
import re
import tempfile
import zipfile
import urllib.parse
import urllib.request
from pathlib import Path
from workbench_packages import PRODUCTS, MAX_BYTES, ReleaseError, digest, verify

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

def discover(trust, installer_revision, *, local_simulation=False, now=None):
    """Never changes the workbench. Temporary verified bundles are discarded."""
    try:
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
        if index['withdrawn']:return {'update_availability':'withdrawn','sequence':index['sequence'],'package':pin}
        with tempfile.TemporaryDirectory(prefix='aibl-discovery-') as directory:
            folder=Path(directory)/index['product'];folder.mkdir()
            for name,limit in [('manifest.json',2*1024*1024),('payload.zip',MAX_BYTES)]:
                (folder/name).write_bytes(fetch(index['package_url'].rstrip('/')+'/'+name,trust['allowed_origin'],local_simulation,limit))
            verify(directory,index['product'],pin)
        return {'update_availability':'verified_candidate','sequence':index['sequence'],'package':pin,'package_url':index['package_url'],'active_use':'unverified'}
    except (ValueError,TypeError,KeyError,OSError,AttributeError,zipfile.BadZipFile) as error:
        return {'update_availability':'unknown','reason':str(error)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trust',required=True);p.add_argument('--installer-revision',required=True);p.add_argument('--local-simulation',action='store_true')
    a=p.parse_args();print(json.dumps(discover(json.loads(Path(a.trust).read_text()),a.installer_revision,local_simulation=a.local_simulation)))
if __name__=='__main__':main()
