# Shared course installer contract

Current proposed Git enrollment is defined in [the Workforce handoff](WORKFORCE-HANDOFF.md).
The `enrollment` registry field selects `agent-workforce/student` for the native
workbench skill. Existing `publisher`, `release_product`, `adopt_skill`, and
`enroll.py` package interfaces below retain their historical semantics. They do
not override current Git enrollment. Publication and cutover require team review.

## Historical package contracts

The explicit [Workforce handoff](WORKFORCE-HANDOFF.md) adds enrollment-time
compatibility for reviewed public-template snapshots. It does not change the
default Essentials setup or activate a published distribution. Its preview binds
the selected client and independent distribution; confirmation composes base,
core and Workforce together while preserving student seeds and Git state.


The explicit [standalone workbench route](STANDALONE-WORKBENCH.md) uses an
independently admitted `aibl.family-lock/v2`: public template plus core, private
student repository, no course invitation at setup. Established-workbench setup
reruns only verify account/ownership and read state, with no student file or Git
state changes. The historical routes described below retain their original
contracts. Source support for the successor does not qualify or activate a new
published default.

For that successor, `enroll.py --check` shows accessible programs only.
`--yes` remains selection only. `--preview --program ID` binds verified inputs
and local Git/file state to a plan; `--apply-plan ID` consumes that exact preview
after student confirmation. Initial installation and interrupted retry reuse
the existing package engine. An installed result reports native verification
pending, with the first action and discovery paths. A later update to existing
package pins requires the student-owned PR flow; enrollment never performs it.

One public entry builds the same workbench for every student, from the public
template `hub.public_template` (`aibuild-lab/my-workbench-template`), and does
not ask which program they are in. SETUP-PROMPT.md step 8 and the shell
launchers without a reviewed pin both run `scripts/hub_setup.py`; so does
`scripts/course_setup.py` when it is given no reviewed lock. No route creates a
new workbench from the retired private `aibuild-lab/agent-essentials` template.
The registry in course-options.json lists every
program with the site ledger's ids, its publisher repository, what it requires
(checked strictly only by the pinned course-distribution route), what it includes (checked
softly and reported) and its adoption skill. Programs join the hub later from
inside the workbench through scripts/enroll.py, which reads that registry, asks
GitHub what the signed-in account can read, confirms with the student, records
the decision in .aibl/enroll.json and names the adoption skill to run; selection is not installation and it never
handles release pins. Adding a program is one line in the registry and no
installer change. An explicit course argument remains for pinned cohort setups. The earlier Agent Native
OS workshop is served by aibuild-lab/workshop-installer, which is frozen; nothing
from that route is installed here.

Every program route uses Git, GitHub CLI, Python, Node, and the command-line
twin of the app the student chose (Claude Code or Codex). The desktop app is
what the student works in; SETUP-PROMPT.md is the guided, app-first entry and
the shell launchers are the terminal fallback. Only the template creates a new independent Git history; Workforce is
adopted as verified files later. Account consent remains in browser flows.
No tokens, student data or private course payloads belong in this repository.

Current tested local baseline: macOS, Python 3.13.12, Claude Code 2.1.228.
Compatibility floors checked in Python: Git 2.28, GitHub CLI 2, Python 3.11,
Node 18, Claude Code 2.1 or Codex CLI 0.140. These are code floors, not certification of every intermediate
version. Native Windows and first-time student setup require separate observed
walkthroughs. No setup-time claim is accepted.

Source validation: scripts/validate-course-setup. The local suite includes all
existing guard tests plus the course-selector, enroll and recovery scenarios.
Source merging is not permission to publish private course content, enroll users
or change device/account permissions. Any existing failed required check must be
resolved; never present missing runtime proof as passed.

Recovery preserves existing folders and private repositories. An interrupted empty clone can finish fetching its verified private origin
and default branch. A partial clone containing work pauses for review; no
student files are deleted. Kernel operation guards release automatically when
the owning process exits. Historical lock files remain held for diagnosis. Reruns recheck live authentication
and private access instead of trusting prior completion flags.

The Python integration suite runs real Git repositories and the actual Python
handoff. Only GitHub, local test transport and account boundaries are simulated.
`tests/test_windows_launcher.ps1` checks PowerShell syntax and interpreter
resolution; running it on macOS does not establish native Windows behavior.

The optional [frozen Workforce route](PINNED-COURSE-DELIVERY.md) binds the exact
AIBL bootstrap and installer files to both accepted product pins. It seeds a
private independent repository from the verified Essentials release archive,
preserving the legacy selector and default-template route for existing callers.
The frozen route must be used when qualifying a named immutable distribution.

Program selection distinguishes repository readability from installed release
records. Unavailable repository access does not prove an absent or pending
invitation. Invalid installed records stop for diagnosis. `--check` and declined
selection write nothing and never refresh the installer. The retained engine
locations and frozen successor identity are specified in PINNED-COURSE-DELIVERY.md.
