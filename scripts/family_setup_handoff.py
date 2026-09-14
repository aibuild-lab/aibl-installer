"""Official exact-distribution setup handoff, called by the admitted native launcher."""
import argparse
import json
from pathlib import Path
import tempfile
from course_setup import command, SetupError, HARNESSES
from frozen_family import acquire, load_distribution
from standalone_setup import setup_standalone


def setup(distribution,sha,harness,workspace=None,name='my-workbench',no_launch=False):
    engine=Path(__file__).resolve().parents[1]
    value=load_distribution(distribution,sha,engine)
    expected=Path.home()/'.aibl/installers'/value['installer']['revision']
    if engine.resolve()!=expected.resolve():raise SetupError('Run the official launcher so the matching enrollment engine is retained at its exact revision')
    try:command(['gh','api','user'])
    except SetupError as error:
        if error.reason!='authentication_missing':raise
        command(['gh','auth','login','--hostname','github.com','--git-protocol','https','--web'],interactive=True)
    # OS and account prompts remain visible. No private program access is needed.
    from standalone_setup import signed_in
    try:signed_in(harness)
    except SetupError as error:
        if error.reason!='authentication_missing':raise
        command(HARNESSES[harness]['login'],interactive=True)
        signed_in(harness)
    workspace=Path(workspace) if workspace else Path.home()/'GitHub'
    folder=workspace/name
    if folder.exists() or folder.is_symlink():
        # Established reruns need neither asset downloads nor workbench writes.
        return setup_standalone(workspace,name,value['family_lock'],None,harness=harness,no_launch=True)
    parent=Path.home()/'.aibl/acquisitions';parent.mkdir(parents=True,exist_ok=True)
    reservation=Path(tempfile.mkdtemp(prefix='workbench-',dir=parent))
    inputs=acquire(distribution,sha,engine,reservation/'verified',['agent-workbench','workbench-core'])
    result=setup_standalone(workspace,name,value['family_lock'],inputs['family_bundles'],harness=harness,no_launch=no_launch)
    return {**result,'distribution_sha256':sha,'retained_distribution':str(reservation/'verified/distribution.json')}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--distribution',required=True);p.add_argument('--distribution-sha256',required=True);p.add_argument('--harness',choices=['claude','codex'],required=True);p.add_argument('--workspace');p.add_argument('--repo-name',default='my-workbench');p.add_argument('--no-launch',action='store_true')
    a=p.parse_args()
    try:print(json.dumps(setup(a.distribution,a.distribution_sha256,a.harness,a.workspace,a.repo_name,a.no_launch),indent=2))
    except (ValueError,OSError) as error:p.exit(1,'Setup paused: '+str(error)+'\n')


if __name__=='__main__':main()
