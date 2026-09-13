# Component versions and package updates

This source extension builds on installer PR #8. It does not change setup,
enrollment, starter ownership, access, or course commands.

| Requirement | Existing foundation | This change |
| --- | --- | --- |
| Approved package trust | Independent reviewed lock, archive/file hashes | Full SemVer precedence and persistent observed version identity history |
| Component packing list | Strict family-package/v1 | Strict v2 components, files, exact dependencies, valid dates, cycle rejection; v1 remains readable |
| Preview | None | Read-only local candidate comparison including prior, actual and incoming files |
| Student preservation | Supplied conflicts and seed preservation | Retain unchanged upstream customizations and deletions, mode edits, identical unowned collision refusal |
| Complete updates | All installed packages reverified | Component changes with local edits and missing required dependencies hold the entire operation |
| Recovery | Kernel lock, journal, verified backups, late-edit refusal | Reused unchanged; verified version history survives rollback |
| Status | Supplied marker | Supplied identity separate from local edits/deletions; update availability unknown offline |

The CLI adds `preview` and `status` to the existing package engine. Preview uses
an independently reviewed local lock and bundles, without account discovery or
writes. Preview is advisory: apply rechecks under the existing operation lock.
A missing dependency requires separate explicit repair; no automatic restore or
new repair command is introduced. No candidate is published by this change.

The local history ledger records verified package and component identities after
all conflicts clear, before transaction writes. It deliberately survives failed
updates and rollback, so version reuse cannot silently introduce different bytes.
It does not establish a remote release history predating this installation.

Synthetic tests cover preservation, v1/v2/future schemas, component immutability,
retirement, required deletion, preview, prerelease order, interruption and backup
integrity. Existing repository gates cover the retained locking implementation.
Native client use, ordinary-student acceptance and Wade-dependent route decisions
remain pending. Supplied identity is not proof of runtime invocation.
