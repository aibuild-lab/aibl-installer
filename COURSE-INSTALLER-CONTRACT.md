# Shared course installer contract

One public entry builds the Essentials hub for every student and does not ask
which program they are in. The registry in course-options.json lists every
program with the site ledger's ids, its publisher repository, what it requires
(checked strictly by the installer for the hub), what it includes (checked
softly and reported) and its adoption skill. Programs join the hub later from
inside the workbench through scripts/enroll.py, which reads that registry, asks
GitHub what the signed-in account can read, confirms with the student, records
the decision in .aibl/enroll.json and names the adoption skill to run; it never
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
