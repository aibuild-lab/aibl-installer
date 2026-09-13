# Candidate discovery and explicit repair

These are operator interfaces, not setup or enrollment changes. Nothing polls,
publishes, provisions trust, sends messages or automatically applies an update.

`python3 scripts/release_discovery.py --trust ADMITTED.json --installer-revision SHA`
reads a separately admitted descriptor. Its exact index digest proves identity,
not authority: never derive admission from the index itself. Updating admission
is a separate future provisioning step, so this is not autonomous latest-release
trust. The descriptor schema is `aibl.release-trust/v1`, with `product`,
`index_url`, `index_sha256`, `allowed_origin`, and positive `minimum_sequence`.
An offline, stale, incompatible, malformed or unverifiable result is `unknown`.
`verified_candidate` means package verification, never active client use.

The index schema is `aibl.release-index/v1`, with `product`, positive `sequence`,
UTC `generated_at` and `expires_at`, existing family `package` pin,
`installer_revision`, boolean `withdrawn`, and `package_url` directory. The
client reads manifest.json and payload.zip there. All URLs share the admitted
HTTPS origin; redirects, credential-bearing URLs and query tokens are refused.
Explicit `--local-simulation` permits admitted file:// fixtures only. Discovery
uses temporary storage and writes no workbench files or installed history.

For repair, preview comparisons already provide prior, actual and incoming
hash/mode records. Save the explicitly reviewed selected path-to-actual-snapshot
map as JSON, then use the existing engine's `repair --root ... --bundles ...
--product ... --reviewed-repair ...` command. Only supplied files from the
currently installed package can be restored. Seed files and retired/unowned
paths are refused. Repair saves local copies, rechecks reviewed state under the
operation lock and reuses the family journal/backups and recover/rollback path.
It never advances package versions. Ordinary editors do not honor installer
locks; detected concurrent edits stop for recovery rather than overwrite them.

Native-client refresh and ordinary-student acceptance require independent
observations. No native or Windows qualification is asserted by these fixtures.
