# Start your AI Build Lab course

**One installer, only the requirements for your program.** Choose Agent
Essentials, Agent Workforce (which includes Essentials, and The Lab for three
months), or The Lab (which includes Essentials). Your workbench is one private
repository on your own GitHub account; every program you join lands in it.

Have a GitHub account, accepted course invitations and supported Claude Code
access ready. You sign into accounts in the browser. Do not paste tokens in chat.
The installer checks tools, creates or resumes your private workbench and opens
Claude in that folder. Claude guides the first useful artifact and Git checkpoint.

## Mac

Open Terminal, paste this launch command and choose your program when asked:

```bash
curl -fsSL https://raw.githubusercontent.com/aibuild-lab/aibl-installer/main/start.sh -o /tmp/aibl-start.sh
bash /tmp/aibl-start.sh
```

macOS 13 or later is required for the course path. Missing Git, GitHub CLI and
Python use Homebrew when needed; its official installer may ask for macOS
consent. Claude uses Anthropic's native installer. Already compatible tools stay
in place. No course Node or Infisical setup is required for Essentials/Workforce.

## Native Windows

Open PowerShell, paste this launch command and choose your program when asked:

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/aibuild-lab/aibl-installer/main/start.ps1 -OutFile "$env:TEMP\aibl-start.ps1"
& "$env:TEMP\aibl-start.ps1"
```

Use Windows 10/11 with Microsoft App Installer (WinGet). Git for Windows,
GitHub CLI and Python install through WinGet with visible OS/package consent;
Claude uses its native installer. No WSL is required. If your device policy
blocks scripts or installations, ask your IT administrator or facilitator for
an approved route. The installer does not change execution policy or device
management settings. Open a fresh PowerShell window if a newly installed tool
is not visible, then rerun this same entry point.

## When setup pauses

- Missing invitation: accept the GitHub invitation for the signed-in account.
  If it is absent, ask the course team to check access, then rerun.
- A bundled program (The Lab with Agent Workforce) reported as "not yet": setup
  continues. It lands in your workbench later, once its invitation arrives.
- Expired authentication: finish the named browser sign-in and rerun.
- Existing folder or repository name: use another name or ask Claude to review
  the existing project. Setup does not delete or replace it.
- Interrupted setup: rerun the same course, folder and repository name. Verified
  work resumes; compatible tools and completed repositories are reused. An empty
  interrupted clone is resumed; a partial folder containing work pauses for review.
- Restricted device: bring the exact nonsecret error to the course team. Do not
  disable safeguards or install an unrelated runtime to get around the policy.

Default project parent is `~/GitHub`, outside cloud-synced folders. Git identity
is set only in the workbench using the account name and GitHub no-reply address
when no local identity exists. Claude can help review that choice later.

Once Claude opens: **Use /aibl-setup and help me make my first useful artifact.**
After Essentials Gate 0, **/aibl-adopt-workforce** brings in the reviewed course
files. That adoption never merges unrelated repository histories.

## Verification status and measurements

The Python state machine has local automated coverage for reruns, missing tools,
authentication, access, name/folder collisions and private-repository checks.
Actual native Mac and Windows setup and first-time student observations are
separate acceptance checks. Do not infer beginner-tested from unit tests.
Local records track Python setup steps, failures, browser interventions and
elapsed time; the first artifact records a later timestamp. OS bootstrap prompts
and time before Python begins are explicitly unmeasured. No automatic telemetry
or timing promise is included.

The earlier Agent Native OS workshop keeps its own installer at
[aibuild-lab/workshop-installer](https://github.com/aibuild-lab/workshop-installer).
[Claude supported installation and access](https://code.claude.com/docs/en/setup).

Facilitators: [end-to-end testing and real-device walkthrough](E2E-TESTING.md).
