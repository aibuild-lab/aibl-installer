# Student-owned update operations

Updates use a newly approved distribution, never polling or a mutable latest
pin. Obtain its verified candidate trio using `scripts/frozen_family.py` and
include every currently installed product. First-time program enrollment uses
the separate guided preview route in STANDALONE-WORKBENCH.md.

From the exact retained installer, request a portable unique operation ID and
run `scripts/student_updates.py prepare --workbench WORKBENCH --operation ID
--family-lock LOCK --family-sha256 INDEPENDENT_DIGEST --family-bundles BUNDLES`.
Before preparation, offer an optional selective `aibl-checkpoint`. Do not stage
all work or require unfinished work to be committed. The preparation worktree
lives outside the active workbench, so unaccepted skills are not discoverable.

Inspect the returned exact package set and complete candidate diff. Then run
`propose --workbench WORKBENCH --operation ID` with the same script. It reconciles
the exact branch and creates at most one grouped PR in the student's own private
repository. Faculty have no routine review or merge role.

Only after the student approves the exact recorded PR head, run
`approve-and-merge --workbench WORKBENCH --operation ID --approved-head SHA`.
Remote base/head changes require fresh review. An uncertain response is resolved
by reading the same PR, not issuing a replacement. Then run
`synchronize --workbench WORKBENCH --operation ID`.

Synchronization verifies the actual merge graph and tree before fast-forwarding.
Changed supplied files, new ignored collisions, unpushed divergence or a later
remote revision stop with all work retained. No reset, stash, force push or
automatic conflict resolution is used. After a remote merge or local-sync
interruption, resume the same operation. Once synchronized, open a fresh session
in the selected app, discover the capabilities and perform the first action.
`local_synchronized` is not native verification or student acceptance.

Local learning data is outside Git. Use `scripts/local_learning_backup.py` for
an explicitly private backup/restore; neither a PR nor Git rollback restores
that state. Never copy local learning data into an update PR.

Operation receipts live in `.aibl-local/updates/`; retain them and their isolated
preparation worktrees until the operation is complete and recovery is no longer
needed. Package history is reconciled only after the exact local merge. This
source contains no unattended automation or fleet-wide student access.
