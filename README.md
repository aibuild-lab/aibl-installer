# AIBL Installer

**[Start here](START-HERE.md)** if you are a student. Everything below is for the curious.

## What it does

One entry point for every AI Build Lab program, and it never asks which one you
are in. You open the app you chose (Claude, or Codex) on your home folder and
paste one prompt. The app checks your machine, installs only what is missing,
guides the two browser sign-ins, switches on the secrets guard and proves it
works, and creates your own private `my-workbench` on GitHub from the public
[AI Build Lab template](https://github.com/aibuild-lab/my-workbench-template),
with three skills already inside it: `aibl-personalize`, `aibl-checkpoint`,
`aibl-enroll`. Then you open that folder in the app and the course begins.

No invitation. No membership. Nothing to accept. The template is public and the
workbench is yours.

## What you end with

```
~/GitHub/my-workbench          on your computer
github.com/you/my-workbench    online, private, only you can see it

my-workbench/
├── CLAUDE.md / AGENTS.md      what the agent reads first, every session
├── context/                   what it knows about you
├── library/                   what you hand it to read
├── work/                      what it makes
├── blueprints/                plans it can follow
└── .claude/skills/  .agents/skills/
    ├── aibl-personalize/      it interviews you and writes your context note
    ├── aibl-checkpoint/       saves or restores exactly the files you choose
    └── aibl-enroll/           selects your program once access is released
```

Programs join that same workbench later, from inside it. `aibl-enroll` shows
the programs your GitHub account can read. Select one and follow its next step.
Check your cohort on the [Learn dashboard](https://learn.aibuildlab.com/) for
its release date, time, and access status. Repository access follows the course's
release schedule, which can differ from the first live session. Before you have
access, that program will not appear; other accessible programs may still be
listed. Run it again whenever you join something new; what is already there
is left alone.

You work in the app you chose. The installer sets up its command-line twin
alongside. Git, GitHub CLI, Python and Node are the shared tools. Your
sign-ins, visible device permissions, project choices, and judgment remain
yours. The secrets guard lives with the app, not the project, so it protects
every folder you ever open.

## For the team

- Student setup, recovery and verification limits: [START-HERE.md](START-HERE.md)
- The prompt the app follows, step by step: [SETUP-PROMPT.md](SETUP-PROMPT.md).
  Step 8 runs `scripts/hub_setup.py`, which creates the workbench from the
  public template `aibuild-lab/my-workbench-template`. No invitation, no
  release pin, no course package.
- The frozen cohort route (hash-pinned engine and packages, for qualification
  runs; not the student default): [STANDALONE-WORKBENCH.md](STANDALONE-WORKBENCH.md),
  [FAMILY-DELIVERY.md](FAMILY-DELIVERY.md), [FROZEN-FAMILY-DISTRIBUTION.md](FROZEN-FAMILY-DISTRIBUTION.md)
- Student-owned updates after enrollment: [STUDENT-UPDATES.md](STUDENT-UPDATES.md)
- What this repository promises each program: [COURSE-INSTALLER-CONTRACT.md](COURSE-INSTALLER-CONTRACT.md)
- Facilitators, end-to-end test and real-device walkthrough: [E2E-TESTING.md](E2E-TESTING.md)
- Frozen cohort distributions (historical route): [PINNED-COURSE-DELIVERY.md](PINNED-COURSE-DELIVERY.md)

Seeded 09-11-2026 from `aibuild-lab/workshop-installer` with its full history.
The earlier Agent Native OS workshop keeps its own installer there; nothing from
that route ships here.

Need help? Ask in your program's channel.
