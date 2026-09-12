# AIBL Installer

[Start here](START-HERE.md)

One entry point for every AI Build Lab program, and it never asks which one
you are in. You open the app you chose on your home folder and paste one prompt;
the app checks your machine, installs only what is missing, guides the two
browser sign-ins, and creates your own private workbench repository with
independent history, then you open it in the app. That workbench is the
Essentials hub.

Supported programs can be adopted into the hub later: **Agent Workforce** (which includes
Essentials, and The Lab for three months) or **The Lab** (which includes
Essentials). When your program starts, one command in your workbench,
`scripts/enroll.py` from these same installer files, reads which program
repositories your GitHub account can read, shows you the list, and on your
yes records the choice and names that program's adoption step. Selection does not install files,
grant access or establish invitation status. The Lab has no verified adoption route yet. Run it
again whenever you join something new; what is already there is left alone.

You work in the app you chose, Claude or Codex; the installer sets up its
command-line twin alongside. Git, GitHub CLI, Python and Node are the shared
tools. Your sign-ins, visible device permissions, project choices, and judgment
remain yours.

- Setup recovery and verification limits: [START-HERE.md](START-HERE.md)
- What this repository promises each program: [COURSE-INSTALLER-CONTRACT.md](COURSE-INSTALLER-CONTRACT.md)
- Facilitators, end-to-end test and real-device walkthrough: [E2E-TESTING.md](E2E-TESTING.md)
- Frozen cohort distributions: [PINNED-COURSE-DELIVERY.md](PINNED-COURSE-DELIVERY.md)

Seeded 09-11-2026 from `aibuild-lab/workshop-installer` with its full history.
The earlier Agent Native OS workshop keeps its own installer there; nothing from
that route ships here.

Need help? Ask in your program's Slack channel.

The ordinary entry is an unpinned setup route. Cohort qualification must use the
independently reviewed frozen distribution, not a moving default branch.
Program selection reuses the retained installer without pulling updates.
