# Reviewed family distribution

This successor supplies exact downloadable package inputs for setup, enrollment
and updates. It does not apply packages, publish releases, grant course access
or verify a native app. Historical distribution and discovery v1 behavior stays
with its existing contracts.

## Admission and release locations

The release owner builds the external distribution after the installer engine
is committed and validated. The official course handoff supplies its exact
download location and independently reviewed SHA-256. The distribution is a
named immutable asset of an installer release targeting that engine commit.
No moving default branch, latest release, downloaded package or installed marker
is a source of trust. A refreshed update recommendation needs a newly admitted
distribution and handoff digest.

Package locators retain the six-field successor family pin: `version`,
`manifest_sha256`, `archive_sha256`, `publisher`, `release_tag`, `release_target`.
The release target is the exact commit reached by dereferencing the release tag.

| Product | Publisher | Tag |
|---|---|---|
| agent-workbench | aibuild-lab/my-workbench-template | vVERSION |
| workbench-core | aibuild-lab/my-workbench-template | workbench-core-vVERSION |
| agent-essentials | aibuild-lab/my-workbench-template | agent-essentials-vVERSION |
| agent-workforce | aibuild-lab/agent-workforce | vVERSION |

Each package release has `manifest.json` and `payload.zip`. Independent tags
allow template, core and free Essentials versions to coexist in one public
repository. Existing release identities are never rewritten.

## Distribution and descriptor fields

All distribution and trust descriptor JSON uses `release_files.encoded` for
deterministic UTF-8 bytes, including its trailing newline. The independent
digest covers those exact bytes.

`aibl.family-distribution/v1` has exactly:

- `installer`: `repository` (`aibuild-lab/aibl-installer`), exact `revision`,
  and `files`, a mapping of installer paths to SHA-256. The required executed
  entry files and verifier modules are listed by `REQUIRED_ENGINE_FILES` in
  `scripts/frozen_family.py`. Additional reviewed tracked files may be included.
- `family_lock`: the complete `aibl.family-lock/v2` object.
- `family_sha256`: SHA-256 of that family's encoded bytes.
- `trust`: one row for every family product, each containing `descriptor` and
  `sha256`. The latter binds the exact encoded descriptor.
- `schema_version`: `aibl.family-distribution/v1`.

Each `aibl.release-trust/v2` descriptor has `product`, `minimum_sequence`,
`index_sha256`, `index_asset` (`index-PRODUCT.json`), and `index_release`.
The latter contains exactly `repository`, `release_tag` and `release_target`,
and names the admitted installer release at the distribution's engine revision.

Each verified `aibl.release-index/v2` has `product`, monotonic `sequence`,
`generated_at`, `expires_at`, the six-field `package` pin, exact
`installer_revision`, boolean `withdrawn`, and `schema_version`. The package
pin must equal the independently admitted family pin before acquisition.
Expiration and withdrawal are enforced; an expired index provides no update
authority and does not disable already installed work.

## Read-only GitHub transport

`github_assets.GitHubAssets` uses only GET requests through `gh api` on
`github.com`. It resolves the exact release tag, rejects drafts and mismatched
repository IDs, dereferences lightweight or annotated tags to the admitted
commit, then downloads the uniquely named uploaded asset by its exact ID.
Metadata and asset bodies have size limits and subprocess timeouts. Package
hashes and archive verification still decide whether bytes are usable.

The existing no-redirect HTTPS adapter remains unchanged. GitHub API asset
delivery is a separate admitted provider operation, including the student's
existing authenticated access to private Workforce assets. No credential or
private payload is embedded in this public installer source.

## Acquisition interface

From the exact retained engine, call:

```python
receipt = frozen_family.acquire(
    distribution_path, independently_reviewed_sha256, engine_root,
    new_external_output_directory, products,
)
```

`load_distribution` first checks the independent distribution digest, all nested
bindings, the exact clean retained engine's Git identity and its file hashes.
The existing frozen launcher retains the engine; this module never fetches,
pulls, replaces or chooses another engine.

Only explicit `products` are downloaded. Fresh setup requests
`agent-workbench` and `workbench-core`, without contacting a private course
publisher. Lesson 8 separately requests `agent-essentials`; its free package
uses the public publisher. Enrollment and updates request the chosen product
plus all installed products that composition will reverify.

After every selected package verifies, and the engine passes a second readback,
the receipt exposes `family_lock`, `family_sha256` and `family_bundles` for
existing setup or preview APIs. It records `verified_candidate` and
`active_use: unverified`. Files are retained in the new external directory.
A failed acquisition never emits a usable trio receipt; preserve partial
outputs and use a new destination for a subsequent reviewed attempt.

The CLI exposes the same interface through `scripts/frozen_family.py` with
`--distribution`, `--distribution-sha256`, `--engine-root`, `--output`, and
repeatable `--product`. Discovery v2 alone remains read-only and discards its
temporary package copies; pass `--descriptor-sha256` with `--trust`.

## Evidence

`tests/test_frozen_family.py` uses synthetic releases, account responses and
package bytes. It covers public-only setup acquisition, optional free and
private packages, exact IDs and targets, annotated tags, duplicates, size and
hash failures, independent admission, expiration, withdrawal, family mismatch,
changed engines and preservation of existing outputs. These tests establish
local source behavior, not live publication, account access or student readiness.
