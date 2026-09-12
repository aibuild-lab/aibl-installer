# Start your AI Build Lab program

**One installer, every program, your own workbench.** You will end with one
private repository on your GitHub account, open in the app you chose. The
installer does not ask which program you are in. Every program you join lands
inside that same workbench later, with one command from inside it; you never
set up a second one.

You need: a GitHub account, the invitation for your program accepted, and an
account for the app you want to work in (Claude, or Codex). Sign-ins happen in
your browser. Nothing here asks you to paste a token or a password into chat.

## Step 0: get Git

The apps cannot start a local session without Git. Do this first.

- **Mac:** open Terminal (Cmd + Space, type Terminal, Enter), type `git --version`,
  press Enter. If a dialog offers to install the command line developer tools,
  click Install and wait for it to finish (10 to 15 minutes, no password).
- **Windows:** install [Git for Windows](https://git-scm.com/downloads/win)
  with the default choices. If the app was already open, close it and reopen it.

## Step 0b: accept your GitHub invitation

Buying a program puts you on its team the moment Learn knows your GitHub name.
The team add sends you a GitHub invitation (email, or the bell at github.com).
Accept it. The installer cannot create your workbench until you do.

## Step 1: download the app you chose, and sign in

- **Claude:** [claude.ai/download](https://claude.ai/download). Sign in, then
  open the Code tab.
- **Codex:** [the Codex app](https://learn.chatgpt.com/codex/app). Sign in
  with your ChatGPT account.

Pick one. The course is the same in both; you can switch later.

## Step 2: open your home folder in the app

When the app asks for a folder, choose the one named after you (your home
folder), not Desktop or Documents.

- **Mac:** in the picker, press Cmd + Shift + H, then choose.
- **Windows:** This PC, Local Disk (C:), Users, then the folder with your name.

If the app asks whether you trust the folder, click Trust. It is your own folder.

## Step 3: paste this, and follow along

```text
You are the AI Build Lab installer assistant. I am a student setting up for my program.

Fetch the full setup procedure from this URL and follow it from the beginning, step by step, without summarizing:

https://raw.githubusercontent.com/aibuild-lab/aibl-installer/main/SETUP-PROMPT.md

Start by greeting me and detecting my operating system and which app you are, as the procedure says. Do not skip steps. Do not ask me what I want to do; the procedure tells you.

If you cannot fetch the URL, say so and I will paste the procedure into chat.
```

The app checks what is already on your machine, tells you what it found and
what it will do, and asks once before it starts. It installs only what is
missing, explains every system prompt before it appears, sends you to your
browser for the two sign-ins, creates your private workbench, and tells you how
to open it in the app. Expect 30 to 60 minutes, longer on a brand-new Mac.

If the app says it cannot open the link: open the URL above in your browser,
select all (Cmd + A or Ctrl + A), copy, and paste the whole procedure into the
chat instead. Same setup, delivered by hand.

## When setup pauses

- **"Accept the course invitation":** step 0b was skipped. Accept it, then
  tell the app to try again. Nothing is lost between attempts.
- **A popup you did not expect:** ask the app what it is. It will tell you what
  to click and why.
- **Existing folder or repository name:** the app reuses it if it is yours; it
  never deletes or replaces anything.
- **Restricted device:** bring the exact error to your program's Slack channel.
  Do not disable safeguards to get around a policy.

Your workbench lives at `~/GitHub/my-workbench`, outside cloud-synced folders,
with a Git identity set only inside it.

## Fallback: the terminal route

If the app cannot run commands on your machine, the same setup runs from a
terminal. It installs the tools and creates the same workbench.

**Mac.** Open Terminal and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/aibuild-lab/aibl-installer/main/start.sh -o /tmp/aibl-start.sh
bash /tmp/aibl-start.sh
```

macOS 13 or later. Missing Git, GitHub CLI, Node and Python use Homebrew,
whose installer may ask for your Mac password in your own Terminal. The
command-line twin of your app uses its native installer. Put `AIBL_HARNESS=codex`
in front of the second line if you chose Codex.

**Native Windows.** Open PowerShell and paste:

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/aibuild-lab/aibl-installer/main/start.ps1 -OutFile "$env:TEMP\aibl-start.ps1"
& "$env:TEMP\aibl-start.ps1"
```

Windows 10 or 11 with WinGet. Git for Windows, GitHub CLI, Node and Python
install through WinGet with visible consent; no WSL. If your device policy
blocks running a downloaded script, ask your program's channel for the approved
route; the installer never changes execution policy. Add `-Harness codex` after
the script path if you chose Codex.

## Verification status

The Python setup has automated coverage for reruns, missing tools, sign-in,
access, name and folder collisions, and private-repository checks. Real native
Mac and Windows runs, and first-time student observations, are separate checks.
Do not read "unit tests pass" as "beginner tested." Local records track setup
steps, failures, browser interventions and elapsed time; no telemetry leaves
the machine.

The earlier Agent Native OS workshop keeps its own installer at
[aibuild-lab/workshop-installer](https://github.com/aibuild-lab/workshop-installer).
[Claude supported installation](https://code.claude.com/docs/en/setup).
[Codex supported installation](https://learn.chatgpt.com/codex/cli).

Facilitators: [end-to-end testing and real-device walkthrough](E2E-TESTING.md).
