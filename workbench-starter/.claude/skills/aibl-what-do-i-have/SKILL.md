---
name: aibl-what-do-i-have
description: "Look around this workbench and say, in plain words, what is here and what it can do. Changes nothing. The proof that setup landed, and the first thing to run in any new session."
---

# What do I have

Look around this workbench and tell the person what is here, in plain words. Change nothing.

## Procedure

1. Say where you are: the full path of this folder, and the name of the folder. Confirm it is a Git project with a remote on GitHub (`git remote get-url origin`) and whether that remote is private (`gh repo view --json isPrivate --jq .isPrivate`). If `gh` is not signed in, say so and move on; do not start a sign-in.

2. Say what is in the three folders. `context/`: the notes you know them by (list the files; if only the README is there, say "I have not met you yet"). `library/`: what they have handed you to read. `blueprints/`: the plans you can follow. One line each.

3. Say which skills came with the workbench: list the folders under `.claude/skills/` (Claude) or `.agents/skills/` (Codex) and one line each on what the skill does, from its description.

4. Say which tools are on this computer, from `git --version`, `gh --version`, `python3 --version` (or `py -3 --version` on Windows), `node --version`, and the app's own command (`claude --version` or `codex --version`). Report a missing one as missing, without installing anything.

5. End with one suggested next action, based on what you found. On day one that is the personalize skill, because `context/` is empty. Later it is whatever the notes say they are working on.

## Result and check

Six short lines, plain words, no jargon the person has not met. Nothing on disk changed. If anything looked wrong (no remote, not private, a tool missing), say which and what to do, and stop there.

## Attribution

Same name and intent as the aibl-what-do-i-have method in the AI Build Lab capability catalog (Hunter Lee Canning, Tyler Fisk). Rewritten for the Agent Native Essentials workbench, which carries no release catalog.
