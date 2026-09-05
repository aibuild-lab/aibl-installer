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
python3 scripts/course_setup.py --course agent-native-workforce \
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
channel. An automated rehearsal requires existing GitHub and Claude Code
sign-ins; it does not automate account consent. Each test round uses a fresh
private practice repository. Omit `--rehearsal-id` only for an actual student
candidate session whose answers remain the student's own.

GitHub qualification uses `gh api user` for the selected account. An invalid
inactive saved account does not block a working selected account. Network,
permission and rejected-credential failures remain unresolved and do not
trigger account changes or repository creation. Only an ordinary student
setup with GitHub CLI's explicit authentication-required result enters the
visible login flow; an automated rehearsal always requires existing access.
The selected account must still match any saved repository binding.

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
