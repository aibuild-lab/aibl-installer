# AIBL Installer changes

## 2026-09-11

- Program registry. `course-options.json` is now `aibl.program-registry/v1`: one line per program with the site ledger's ids (`agent-essentials`, `agent-workforce`, `the-lab`), the publisher repository, what each program requires (checked strictly) and includes (checked softly and reported as found or not yet). The menu is generated from it and asked by `course_setup.py` after tools are ready; the launchers no longer carry a hard-coded menu. The Lab is a program of its own and is included with Agent Workforce. The pinned course id follows the registry (`agent-workforce`); release product ids are unchanged.
- Seeded `aibuild-lab/aibl-installer` from `workshop-installer` at 64130d9 with full history. Removed the legacy Agent Native OS route (install.mjs, install.sh, install.ps1, SETUP-PROMPT.md, MANUAL-INSTALL.md, the migration and repo-prep scripts, their test, and the generated OpenWiki pages); it stays in `workshop-installer`, frozen. The course menu is Essentials and Agent Workforce. Every installer reference now names `aibuild-lab/aibl-installer`, so any existing frozen distribution lock is invalid by design and must be regenerated.

## 2026-09-06

- PR #31 adds an explicitly pinned local course-candidate setup route and desktop handoff. It prepares practice files from reviewed bundles while preserving published distribution paths. Prepared files do not prove native client execution or student learning.
