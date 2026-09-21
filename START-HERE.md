# Start your AI Build Lab program

**One installer, every program, your own workbench.** You will end with one
private repository on your GitHub account, called `my-workbench`, open in the
app you chose, with three skills already inside it. No invitation, no
membership, nothing to accept. Your program joins that same workbench later,
from inside it, with one command.

## You need

- A computer you are allowed to install things on. A work laptop may say no.
- A free GitHub account, signed in at github.com in your browser.
- An account for the app you want to work in, on a paid plan: **Claude**, or
  **Codex** (inside the ChatGPT app). Pick one. The course is the same in both,
  and you can switch later.
- About an hour. Most of it is watching.

Nothing here asks you to paste a token or a password into chat. Every sign-in
happens in your browser.

## Step 0: get Git

The apps cannot start a local session without Git. Do this first, before you
even download the app.

- **Mac:** open Terminal (Cmd + Space, type Terminal, Enter), type `git --version`,
  press Enter. If a dialog offers to install the command line developer tools,
  click Install and wait for it to finish (10 to 15 minutes, no password).
  Those tools are Git.
- **Windows:** install [Git for Windows](https://git-scm.com/downloads/win)
  with the default choices. If the app was already open, close it and reopen it,
  or it will still think Git is missing.

## Step 1: download the app you chose, and sign in

- **Claude:** [claude.ai/download](https://claude.ai/download). Sign in, then
  open the Code tab (the small code icon at the top of the sidebar).
- **Codex:** [the ChatGPT app](https://learn.chatgpt.com/codex/app). Sign in
  with your ChatGPT account, then choose Codex from the dropdown at the top left.

## Step 2: open your home folder in the app

When the app asks for a folder, choose the one named after you (your home
folder), not Desktop or Documents, and nothing inside Dropbox, OneDrive,
iCloud or Google Drive.

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
what it will do, and asks once before it starts. Then it installs only what is
missing, explains every system prompt before it appears, sends you to your
browser for the two sign-ins, installs the secrets guard and proves it works,
creates your private workbench from the public AI Build Lab template with its
three skills, and tells you how to open it. Expect 30 to 60 minutes, longer on
a brand-new Mac.

If the app says it cannot open the link: open the URL above in your browser,
select all (Cmd + A or Ctrl + A), copy, and paste the whole procedure into the
chat instead. Same setup, delivered by hand.

## Later: update your workbench

Your workbench keeps working after setup, and its skills and programs get better
over time. When the team says an update is out, or whenever you want to check,
open the app on your `my-workbench` folder and paste this:

```text
You are the AI Build Lab update assistant. I am a student and this session is open on my workbench.

Fetch the update procedure from this URL and follow it from the beginning, step by step, without summarizing:

https://raw.githubusercontent.com/aibuild-lab/aibl-installer/main/UPDATE-PROMPT.md

Say what you are about to do before each step. Do not install anything, do not re-run setup, and do not touch anything I made.

If you cannot fetch the URL, say so and I will paste the procedure into chat.
```

It refreshes the workbench's own skills from the template, then, if your
workbench has the `aibl-update` skill, brings every program you have joined up
to date, showing you what changes before anything lands. A minute or two.
Do not re-run the setup prompt to get updates; setup never rewrites a workbench
that already exists.

## Connect Workforce after Essentials

Open the same `my-workbench`, run `aibl-enroll`, and choose Workforce. It comes
from `aibuild-lab/agent-workforce`, branch `student`. Review and approve the
changes, then start a new session and run `aibl-workforce`. Existing package
installations use the same comparison and approval step. Keep your Camp/OS
projects separate. See [the complete handoff](WORKFORCE-HANDOFF.md).

## When setup pauses

- **"GitHub is still preparing the new repository":** GitHub takes a moment to
  fill in a new repository. Wait a minute and tell the app to run that step
  again. Nothing needs to be undone.
- **A popup you did not expect:** ask the app what it is. It will tell you what
  to click and why.
- **You already have a workbench:** it is reused exactly as it is. Nothing is
  rewritten, nothing is deleted. If it came from an older template and is
  missing the supplied skills, use the update prompt above, then restart your
  session. Do not repeat setup.
- **A `my-workbench` that is not yours:** if a folder or repository with that
  name belongs to something else, the app stops and shows you what it found.
  Nothing is replaced. You can pick another name.
- **Restricted device:** bring the exact error to your program's channel. Do
  not disable safeguards to get around a policy.

## What you end with

- `~/GitHub/my-workbench` on your computer, and `github.com/you/my-workbench`
  online, marked Private. Only you can see it.
- Inside it: `context/` (what the agent knows about you), `library/` (what you
  hand it to read), `work/` (what it makes), `blueprints/` (plans it can
  follow), and three skills under `.claude/skills/` and `.agents/skills/`:
  `aibl-personalize`, `aibl-checkpoint`, `aibl-enroll`.
- Type `/` in Claude, or `$` in Codex, and the three skills are listed. That
  is your proof that everything landed.

Your workbench is ready even if your course access has not opened. Check your
cohort on the [Learn dashboard](https://learn.aibuildlab.com/) for its release
date, time, and access status. Repository access follows your course's release
schedule, which can differ from the first live session. Before you have access,
that program will not appear in `aibl-enroll`; other accessible programs may
still be listed. Once access opens, select the program and follow its next step.
You never set up a second workbench.

## Fallback: with a person

If the app cannot run commands on your machine, ask in your program's channel
and a person will finish setup with you. They follow the same procedure by
hand: install Git, Node, the GitHub CLI and Python, sign you in to GitHub in
your browser, then run the same two commands the app would have run, from a
terminal in your home folder:

```bash
git clone https://github.com/aibuild-lab/aibl-installer ~/GitHub/aibl-installer
python3 ~/GitHub/aibl-installer/scripts/hub_setup.py --harness claude
```

(Windows: PowerShell, `$HOME\GitHub\aibl-installer` and `py -3`; `--harness codex`
if you chose Codex.) Same tools, same workbench, same three skills.

## Verification status

The Python setup has automated coverage for reruns, missing tools, sign-in,
name and folder collisions, and private-repository checks. Real native Mac and
Windows runs, and first-time student observations, are separate checks. Do not
read "unit tests pass" as "beginner tested." Local records track setup steps,
failures, browser interventions and elapsed time; no telemetry leaves the
machine.

The earlier Agent Native OS workshop keeps its own installer at
[aibuild-lab/workshop-installer](https://github.com/aibuild-lab/workshop-installer).
[Claude supported installation](https://code.claude.com/docs/en/setup).
[Codex supported installation](https://learn.chatgpt.com/codex/cli).

Facilitators: [end-to-end testing and real-device walkthrough](E2E-TESTING.md).
