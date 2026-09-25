# Agent family successor candidate

The separate template route is explicit until release and platform qualification.
Frozen distributions remain available unchanged. The historical default route,
which created a workbench from the private `aibuild-lab/agent-essentials`
template, is retired (09-25-2026); without a lock, setup now builds the
public-template workbench. Existing Essentials-template workbenches are still
accepted in place, as below.
This is source preparation, not activation of an unqualified student route.

The registry lists agent-workbench independently from the agent-essentials course
package. Internal scripts/family_packages.py builds three versioned packages.
A trusted aibl.family-lock/v1 binds exact clean installer revision, each package's
version, publisher, manifest/archive hashes and historical compatibility mappings.
The lock is delivered independently of the package archives. Never trust a lock
found inside an untrusted package.

Fresh or existing setup:

```sh
python3 scripts/course_setup.py --course agent-essentials --harness codex \
  --family-lock /private/reviewed/family-lock.json \
  --family-sha256 REVIEWED_DIGEST --family-bundles /private/reviewed/bundles
```

Fresh setup creates a private independent repository from agent-workbench and
then installs Essentials. Existing Essentials-template repositories are accepted
in place. The installer rechecks ownership/private remote and retains Git history,
uncommitted files and unpushed commits. Student-owned roots and context are seeds.
The existing legacy installed manifest supplies managed-file hashes on transition;
legacy tools outside the successor package are retained for review, never deleted.

Later access/adoption and updates use the same workbench and reviewed family lock:

```sh
python3 scripts/workbench_packages.py apply --root /path/to/my-workbench \
  --lock /private/reviewed/family-lock.json --sha256 REVIEWED_DIGEST \
  --bundles /private/reviewed/bundles --product agent-workforce
```

The new publisher is aibuild-lab/agent-workforce. Historical agent-native-workforce
pins retain their old publisher, product and verifier. Do not rewrite historical
receipts or run the old adoption skill against a new package format. The package
CLI is local application only; enrollment/access verification precedes distribution
and does not itself grant access. Ordinary student access remains unobserved.

A family update re-verifies every installed product against the selected tuple.
Changed supplied files stop before writes. Review their diff, save a separate copy,
restore only the named supplied bytes when approved, then retry the transaction.
Personal roots, custom skills and local learning records are preserved. Record the
returned rollback identity. Recover an interrupted update before any new operation:

```sh
python3 scripts/workbench_packages.py recover --root /path/to/my-workbench
python3 scripts/workbench_packages.py rollback --root /path/to/my-workbench --backup ID
```

Rollback verifies backups and refuses to overwrite later student edits. Backups
are local-only. A copied workbench or Git clone alone does not prove local-state
recovery. Local-state backup, native app discovery, ordinary-account enrollment,
platform observations, teaching captures and LMS publication remain separate gates.

Provenance: scripts/release_files.py is an unchanged copy of Internal's MIT-reviewed
repository-build/tools/v3/aibl_release.py at 966c2f08d97c76b3d8c9571b9f6a16de3f7207ce.
Its license is licenses/release-files-MIT.txt. The successor reuses only its atomic
write, safe-path and kernel-lock primitives; historical release rules stay intact.

Local learning backup uses scripts/local_learning_backup.py. Close active course
sessions first. Choose a new private file outside the repository, retain the
returned independent SHA-256, and copy it to approved private storage yourself.
The command never uploads data. Restore verifies hashes and creates missing files;
existing different responses are preserved for review. This scope is the actual
.aibl-local/learning tree, not secrets, machine settings or automated rehearsals.

```sh
python3 scripts/local_learning_backup.py backup --root /path/to/my-workbench --file /private/learning.zip
python3 scripts/local_learning_backup.py restore --root /path/to/my-workbench --file /private/learning.zip --sha256 RECORDED_DIGEST
```

The lock also binds template_revision, the exact agent-workbench commit. Fresh
setup checks that upstream revision before creation and verifies cloned seed
bytes against the reviewed template package before installing Essentials.

A portable local rehearsal is available from clean committed source:

```sh
python3 scripts/rehearse_family.py --internal-source /path/to/Internal --legacy-source /path/to/agent-essentials --output /private/new-rehearsal
```

It uses local bare Git remotes, a pushed checkpoint plus an unpushed commit,
uncommitted files and separate local state. It invokes the actual composed
setup/learning/capability helpers, then adds and rolls back Workforce. It never
creates GitHub repositories or substitutes for an ordinary student walkthrough.

Windows privacy qualification must inspect the chosen directory's ACL. POSIX
mode 0600 checks do not establish Windows account isolation. File-update recovery
normalizes the Windows read-only semantics; native Windows observation remains open.

Concurrent proposal: Wade PR7 at aade4944f07ceb573de419928948d023eee7bb02
proposes installer-owned starter content and no template or invitation requirement.
This successor follows Hunter's explicit separate private-template/course-package
sprint instruction. PR7 is preserved, not imported or represented as accepted.
Its no-invitation onboarding goal and new teaching entry must be reconciled before
choosing the published default. PR1-6 history is integrated unchanged.
