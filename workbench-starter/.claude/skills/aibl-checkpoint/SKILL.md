---
name: aibl-checkpoint
description: "Save a checkpoint: a named snapshot of the workbench, kept on this computer and on GitHub. Explain what changed in plain words first. Also brings a file back from an earlier checkpoint when asked."
---

# Checkpoint

A checkpoint is a snapshot of the whole workbench with a name on it. Once it is saved in two places, this computer and GitHub, the work cannot be lost, and any file can be brought back from any earlier checkpoint.

## Procedure

1. Say what changed since the last checkpoint, in plain words: which files are new, which changed, one line each (`git status --porcelain`, `git diff --stat`). If nothing changed, say so and stop.

2. Never include a secret. If a changed file looks like it holds a password or a key (`.env`, anything named "secret" or "token", a long random string), leave it out, say why, and go on with the rest. `.aibl-local/` is never included.

3. Propose a one-line label that says what this checkpoint is, in their words ("the interview", "fixed the line about my role"). Use theirs if they give one.

4. Save it: `git add -A` (minus anything from step 2), `git commit -m "<label>"`, then `git push`. If push is refused because the sign-in expired, say so and tell them the sign-in happens in the browser; never ask for a code in the chat.

5. Report in two lines: the label and the short commit id, and "saved in two places: this computer and github.com/<you>/<repo>."

## Bringing a file back

When they ask for an earlier version: list the last ten checkpoints by label (`git log --oneline -10`), ask which one, then restore only the file they name from it (`git checkout <id> -- <file>`). Say what came back and that nothing else moved. Then offer a new checkpoint so the restore itself is saved.

## Result and check

`git status` is clean, the last commit carries their label, and `git log origin/main -1` matches the local one. They can say what a checkpoint is in one sentence.

## Attribution

Same name and intent as the aibl-checkpoint method in the AI Build Lab capability catalog (Hunter Lee Canning, Tyler Fisk). Rewritten for the Agent Native Essentials workbench.
