# Test the complete student setup

State: implementation hardening; real-device and beginner acceptance remain open.
Source: repository-owned tests and observed local runs, 2026-09-04.

## Automated checks

Run `scripts/validate-course-setup`. It includes unit tests, real local Git/Python
integration, lost creation-response recovery, interrupted-clone recovery,
student-work preservation and process-termination/duplicate-writer tests, plus
the retained workshop and hook suites. No GitHub repositories or accounts are
created by these tests. Browser sign-in and GitHub responses are simulated.

With an available PowerShell runtime, run
`pwsh -NoProfile -File tests/test_windows_launcher.ps1`. It parses the launcher
and checks actual Python interpreter resolution on that host. This is not an
OS installation test and does not prove Windows execution-policy compatibility.

The internal course repository's `scripts/e2e_student_journey.py` connects this
setup implementation to verified Essentials and Workforce bundles, real local
Git commits/push/restore, five cases, recovery, rollback and client transfer.
Use its independently reviewed release pins and exact source identities.
It labels the simulated account/network boundaries and never supplies human approval.

## Real student walkthrough

Use a fresh macOS 13+ account and a native Windows 10/11 account with approved
device permissions. Use student-level private course access, not an organization
administrator's access. Open START-HERE, select Workforce, and record:

1. Every manual action, OS prompt, failure and recovery, beginning before Python
   is available. Capture actual tool versions, account-access state and time.
2. Browser GitHub and Claude sign-in. Do not paste tokens into chat or screenshots.
3. One private repository created from Essentials, a verified local clone and
   repository-specific Git identity. Rerunning must reuse it and preserve work.
4. Claude opened in that project, a useful artifact, an explained checkpoint,
   reviewed push, scoped restore and fresh-session continuation.
5. Verified Workforce adoption after Gate 0, visible approval for native project
   configuration, and actual discovery/use of the student's lead and specialist.
6. Rejection, repair, evaluator judgment and the student's own distinct decision.
7. Interrupted work, a compatible update, rollback, new client context/history
   and an authorized collaborator's private-remote continuation.

Pause at actual account or device consent. Never disable organization controls
or modify global Git identity to make a test pass. A `.ps1` entry cannot run when
an effective Restricted or applicable signing policy rejects it. This remains a
Windows onboarding acceptance item until a supported, approved launch path is
observed on the target device. Do not call parser success beginner readiness.

For failures, preserve the project and capture a short nonsecret error plus the
step. Distinguish missing invitations from network failure. A damaged progress
file or historical lock needs diagnosis, not deletion or a second repository.

## Current limits

No fresh Windows OS installation, live student invitation/browser flow, or
first-time student session has been observed in this build environment. No
setup-time promise is supported. Local measurements omit the pre-Python OS
bootstrap; the walkthrough must supply those observations. Existing compatible
process PATH entries are preserved, and Python resolves to a verified executable
rather than assuming that the first `python` alias is the new installation.

Primary references:
- [Claude setup and supported platforms](https://code.claude.com/docs/en/setup)
- [Microsoft execution-policy behavior](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies)

## Failure and version receipts

Each Python attempt records PASS, FAIL, IN_PROGRESS or NOT_RUN for nine stages,
the last proven stage, failed stage, bounded failure domain and safe recovery.
An interrupted process can leave IN_PROGRESS; that is not a passing stage.
The receipt records executed setup/catalog hashes, observed installer revision
and dirty state, the platform launcher hash when supplied, and the observed
workbench commit/tree. These identify observations, not a pinned distribution.
The browser bootstrap, installer clone and template creation still follow their
current default branches. Record that entire resolved tuple during qualification;
course release pins alone do not qualify the full installation chain. Pre-Python
failures still need the facilitator's walkthrough record.
