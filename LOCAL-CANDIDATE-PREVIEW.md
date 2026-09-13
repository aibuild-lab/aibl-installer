# Local candidate workbench preview

This explicit route tests an unmerged local course candidate. It creates a
real private practice repository using the existing GitHub identity and the
current frozen setup/recovery flow. It does not publish a course release,
modify an existing channel, enroll students or change global configuration.

The operator supplies an independent distribution lock and its SHA-256. The
lock pins this exact clean installer commit, its five setup-file hashes and
both course products. A candidate bundle directory contains:

```text
candidate/
  agent-essentials/manifest.json
  agent-essentials/payload.zip
  agent-native-workforce/manifest.json
  agent-native-workforce/payload.zip
```

A saved published setup and a saved local candidate keep their original
delivery modes. Changing mode requires a fresh project name; a preview attempt
against an existing published setup fails before account calls or project
changes, and its original published setup can still resume. Candidate transport
also requires matching installed candidate provenance before writing a locator.

Use an actual supported Python 3.11+ executable. From the pinned clean installer:

```sh
python3 scripts/course_setup.py --course agent-workforce \
  --preview-bundle /absolute/path/candidate \
  --distribution-lock /absolute/path/independent-distribution.json \
  --distribution-sha256 REVIEWED_SHA256 \
  --workspace /absolute/local/practice \
  --repo-name UNIQUE_PRIVATE_PRACTICE_NAME \
  --rehearsal-id UNIQUE_TEST_ID --no-launch
```

The capitalized values are placeholders the operator resolves from reviewed
inputs. The preview verifies both local product payloads before account or
repository actions. It never downloads a candidate tag or consults a current
channel. The default CLI route requires existing GitHub and Claude Code sign-ins
for an automated rehearsal; it does not automate account consent. Each test
round uses a fresh private practice repository. Omit `--rehearsal-id` only for
an actual student candidate session whose answers remain the student's own.

GitHub qualification uses `gh api user` for the selected account. An invalid
inactive saved account does not block a working selected account. Network,
permission and rejected-credential failures remain unresolved and do not
trigger account changes or repository creation. Only an ordinary student
setup with GitHub CLI's explicit authentication-required result enters the
visible login flow; an automated rehearsal always requires existing access.
The selected account must still match any saved repository binding.

## Claude Desktop files handoff

For a separate native Claude Desktop preview, add `--desktop` to the explicit
Python command above. This option is supported only with `--preview-bundle`
for the Workforce local candidate, which starts with Essentials. It verifies
the frozen local inputs, Git, GitHub CLI and Python, then uses the same selected
GitHub account, private repository,
seed push/readback, local Git identity and installed student-context gates.
It never calls Claude CLI for a version, authentication or session, and does
not open an application, enroll a working directory or change credential routes.

The returned result and saved attempt stop at `files_ready_for_desktop`, with
`last_proven_stage=student_context`. Both CLI stages remain `NOT_RUN`.
`desktop_authentication`, `desktop_session` and `native_runtime` are all
`NOT_OBSERVED` in both records. The result includes the exact project path,
observed commit and tree, `/aibl-teach` and the handoff prompt. An automated
rehearsal keeps its explicit rehearsal ID, actor and `course_credit=false`.
GitHub, source, seed or student-context failures still stop setup as `blocked`.

Open that project in the existing native Desktop session and use the returned
handoff prompt. The end-to-end operator records actual Desktop version,
permissions, authentication, session and teaching observations separately.
A files handoff does not establish any of those observations or completion of
the learning exercises. If Desktop is unavailable, the files remain prepared
while its native session remains unobserved.

Setup freezes `client=claude_desktop` before its tool and account calls.
Retries preserve the selected client and existing work. A saved state without
a client field keeps the legacy CLI meaning. A different frozen client, or a
different client for an existing repository/distribution, requires a fresh
project name. Prior CLI attempts and their exact distribution stay intact.
The default CLI route remains unchanged: `--no-launch` still verifies Claude
CLI authentication. With `--desktop`, `--no-launch` is redundant because this
route always ends with the files handoff.

The seed flow initializes an independent local history, pushes it to the new
private repository and verifies the remote HEAD. Setup retains the actual
`student_observed_commit` in its attempt provenance. To qualify a real clone,
perform this separate round-trip for each observed test round:

```sh
gh repo clone ACCOUNT/UNIQUE_PRIVATE_PRACTICE_NAME /absolute/local/fresh-clone
git -C /absolute/local/fresh-clone rev-parse HEAD
```

Compare that HEAD with the pushed seed HEAD before proceeding. Keep the seed
and its evidence. Open the fresh clone, then reattach the local-only candidate
locator and initialize a separate automated learning namespace:

```sh
python3 scripts/aibl_release.py candidate-relink --root . \
  --bundle /absolute/path/candidate \
  --distribution-lock /absolute/path/independent-distribution.json \
  --distribution-sha256 REVIEWED_SHA256 --json
python3 scripts/aibl_learning.py init-rehearsal --root . \
  --rehearsal UNIQUE_TEST_ID --actor automated_test
```

Relinking verifies both products, exact source revision and the project's
frozen distribution. Moving or recloning does not silently choose another
bundle. Local locator, rehearsal marker, raw responses and receipts stay under
ignored `.aibl-local/`; Git never transports them. A missing original bundle
requires an explicit verified relink to identical pinned bytes.

The tutor uses the installed mission catalog and normal checkpoint mechanisms
with `--rehearsal UNIQUE_TEST_ID --actor automated_test` on every learning and
project helper call. The resulting schema is `aibl.learning-rehearsal/v1`, with
`test_answers`, explicit `test_choice` and `course_credit=false`. It cannot
write human review records, export LMS student summaries or claim human
comprehension, approval or credit. Test artifacts and native observations must
still actually exist; marking a record automated does not excuse inventing
execution or bypassing the mission prerequisites.

After the real rehearsal Essentials evidence and explicit test adoption choice,
use `scripts/aibl_release.py candidate-verify --root . --product agent-native-workforce --json`
then `candidate-apply` with the same arguments. These use the existing release
verifier, collision checks, interrupted-transaction recovery and rollback.
The caller's existing authorization covers adoption in the isolated test
project; the test choice itself grants no account or external action authority.

Source checks: `python3 -m unittest discover -s tests -p 'test_*.py'` and
`scripts/validate-course-setup`. Current Mac UI observations are a separate
qualification owned by the end-to-end operator. Portable tests do not qualify
native Windows or establish a real student's outcome.
