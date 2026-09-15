# Selected local learning recovery

This is a separate local operation, not a Git checkpoint, package rollback,
course completion receipt, or agent-native verification. It makes no network
calls and does not reset Git. Package/update history and unselected learning
files are outside its restore scope.

Close active learning sessions before backup or restore. Use the retained,
reviewed installer and an existing workbench root. Choose individual regular
files below `.aibl-local/learning/`, not all of `.aibl-local`. Other local state
may include package history or secrets and is deliberately excluded. File
contents never appear in command output; names, modes, hashes and status do.

## Back up an explicit selection

Choose a new file outside the workbench, in a private local directory that is
not cloud-synced. Replace the illustrative paths below with actual paths.
Repeat `--path` for each selected learning file.

```sh
python3 scripts/local_learning_backup.py backup \
  --root /absolute/my-workbench \
  --file /absolute/private-backups/lesson-backup.zip \
  --path .aibl-local/learning/progress.json
```

Retain the returned archive SHA-256 separately with the backup. The archive
does not encrypt its contents. On POSIX, archive and retained snapshot files
are created with mode `0600`, transaction directories with `0700`. On Windows,
those modes are not an ACL or privacy guarantee: use a user-private directory
and qualify its actual ACLs on the native device before use. No tool here
changes device policy or account permissions.

The tool refuses symlinks, traversal, existing backup destinations, and a
backup inside the workbench. Use real directory paths, not symlink aliases
such as macOS `/var` when its real path is `/private/var`. Archives and total
uncompressed content are bounded at 32 MiB, with at most 4096 selected files.
This is intentionally not a general backup system.

## Review and explicitly confirm a restore

```sh
python3 scripts/local_learning_backup.py preview \
  --root /absolute/my-workbench \
  --file /absolute/private-backups/lesson-backup.zip \
  --sha256 ARCHIVE_SHA256 \
  --path .aibl-local/learning/progress.json \
  --plan /absolute/private-backups/restore-review.json
```

Preview does not change the workbench. It creates the explicitly requested
external review file, binding the workbench path, exact archive digest,
selection, and each current and replacement file's hash/mode. Omitting
`--path` at preview selects every file in that explicit archive. Review the
selection and returned before/after hashes with the student. Then pass the
exact returned review digest and explicit confirmation:

```sh
python3 scripts/local_learning_backup.py apply \
  --root /absolute/my-workbench \
  --file /absolute/private-backups/lesson-backup.zip \
  --sha256 ARCHIVE_SHA256 \
  --plan /absolute/private-backups/restore-review.json \
  --review-sha256 REVIEW_SHA256 --confirm
```

Changed learning bytes or modes after preview stop the operation. Before
replacing any learning file, the tool retains the superseded bytes and the
selected backup bytes under `.aibl-local/learning-recovery/TRANSACTION/`, then
records a separate `.aibl-local/learning-restore.json` journal. It reuses the
package engine's path checks, atomic file replacement and process guard, but
does not consume or replace package recovery records. The transaction ID is
the exact restore-review digest. Do not delete its records to clear a hold.

An interrupted preparation before the journal can retry the same confirmed
apply, only while the reviewed current files still match. Once the journal
exists, complete that already-confirmed operation with:

```sh
python3 scripts/local_learning_backup.py recover --root /absolute/my-workbench
```

Recovery only accepts each selected file in its recorded before or after
state. It refuses any different later edit, leaving that edit and the pending
transaction intact for diagnosis. No force option, automatic discard, or Git
reset is supplied. A completed apply retried after a lost response returns
`already_restored` without rewriting matching files. The process guard
serializes these installer operations; it does not lock out arbitrary editors,
so keep other learning sessions closed throughout.

## Review an undo

```sh
python3 scripts/local_learning_backup.py undo-preview \
  --root /absolute/my-workbench --transaction TRANSACTION \
  --plan /absolute/private-backups/undo-review.json

python3 scripts/local_learning_backup.py undo \
  --root /absolute/my-workbench \
  --plan /absolute/private-backups/undo-review.json \
  --review-sha256 UNDO_REVIEW_SHA256 --confirm
```

Undo also refuses later edits. It restores the superseded local bytes and
original modes. A selected file that was absent before restore is removed only
when it still matches the restored snapshot; its backup bytes remain in the
transaction. Interrupted undo uses the same `recover` command. Unrelated
files and all transaction history remain. A restored-and-undone transaction
is a consumed operation, not an automatic toggle or reusable force-restore.

## Historical compatibility and evidence

Existing `backup(root, destination)` callers can still explicitly back up the
whole learning directory, using the existing `aibl.local-learning-backup/v1`
archive format. Historical CLI `restore --file ... --sha256 ...` remains
missing-file-only and refuses differing existing bytes. The reviewed route
accepts those v1 archives without migration.

Run `python3 -m unittest discover -s tests -p 'test*learning*.py'` for the
focused synthetic checks. They exercise selection isolation, confirmation,
hash/mode drift, every durable apply-write interruption, undo, retained-byte
damage, symlinks, and later-edit preservation. They are not native Windows
ACL evidence, ordinary-student evidence, or proof that a learning app loaded
the restored state. Those remain separate qualification and human-use gates.
