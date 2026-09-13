#!/bin/bash
# AIBL installer, macOS entry. The earlier Agent Native OS route lives in aibuild-lab/workshop-installer, frozen.
set -euo pipefail
export AIBL_BOOTSTRAP_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
COURSE="${1:-}"
HARNESS="${AIBL_HARNESS:-claude}"
case "$HARNESS" in claude|codex) ;; *) echo 'AIBL_HARNESS must be claude or codex.'; exit 1;; esac
DISTRIBUTION_LOCK="${2:-}"
DISTRIBUTION_SHA256="${3:-}"
INSTALLER_COMMIT="${4:-}"
LAUNCHER_SHA256="${5:-}"
if [[ -n "$DISTRIBUTION_LOCK$DISTRIBUTION_SHA256$INSTALLER_COMMIT$LAUNCHER_SHA256" ]]; then
  if [[ "$COURSE" != agent-workforce || ! -f "$DISTRIBUTION_LOCK" || ! "$DISTRIBUTION_SHA256" =~ ^[a-f0-9]{64}$ || ! "$INSTALLER_COMMIT" =~ ^[a-f0-9]{40}$ || ! "$LAUNCHER_SHA256" =~ ^[a-f0-9]{64}$ ]]; then echo 'Pinned setup needs the course, reviewed lock file, lock digest, installer commit and launcher digest.'; exit 1; fi
  if [[ "$(shasum -a 256 "$AIBL_BOOTSTRAP_PATH" | cut -d' ' -f1)" != "$LAUNCHER_SHA256" || "$(shasum -a 256 "$DISTRIBUTION_LOCK" | cut -d' ' -f1)" != "$DISTRIBUTION_SHA256" ]]; then echo 'Pinned launcher or distribution lock bytes differ. Download the reviewed files again.'; exit 1; fi
  DISTRIBUTION_LOCK="$(cd "$(dirname "$DISTRIBUTION_LOCK")" && pwd)/$(basename "$DISTRIBUTION_LOCK")"
fi
# The installer builds the Essentials hub for everyone; programs join the workbench later through scripts/enroll.py. An explicit course argument is kept for pinned cohort setups.
if [[ "$(uname -s)" != Darwin ]]; then echo 'Use start.ps1 on native Windows. This entry supports macOS.'; exit 1; fi
if [[ "$(sw_vers -productVersion | cut -d. -f1)" -lt 13 ]]; then echo 'macOS 13 or later is required.'; exit 1; fi
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! git --version >/dev/null 2>&1 || ! command -v gh >/dev/null 2>&1 || ! command -v node >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3,11))' >/dev/null 2>&1; then
 if ! command -v brew >/dev/null 2>&1; then
  echo 'Homebrew installs missing prerequisites. Its official installer may ask for macOS consent.'
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
 fi
fi
if ! git --version >/dev/null 2>&1; then brew install git; fi
if ! command -v gh >/dev/null 2>&1; then brew install gh; fi
if ! command -v node >/dev/null 2>&1; then brew install node; fi
PYTHON=python3
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3,11))' >/dev/null 2>&1; then
 brew install python@3.13
 PYTHON="$(brew --prefix python@3.13)/bin/python3.13"
fi
if [[ "$HARNESS" == claude ]] && ! command -v claude >/dev/null 2>&1; then
  curl -fsSL https://claude.ai/install.sh -o "${TMPDIR:-/tmp}/aibl-claude-install.sh"
  bash "${TMPDIR:-/tmp}/aibl-claude-install.sh"
fi
if [[ "$HARNESS" == codex ]] && ! command -v codex >/dev/null 2>&1; then
  curl -fsSL https://chatgpt.com/codex/install.sh -o "${TMPDIR:-/tmp}/aibl-codex-install.sh"
  sh "${TMPDIR:-/tmp}/aibl-codex-install.sh"
  export PATH="$HOME/.codex/bin:$PATH"
fi
# Keep the enrollment engine after Terminal closes. Existing files are never reset.
INSTALLER_DIR="$HOME/GitHub/aibl-installer"
if [[ -n "$INSTALLER_COMMIT" ]]; then INSTALLER_DIR="$HOME/.aibl/installers/$INSTALLER_COMMIT"; fi
if [[ -L "$INSTALLER_DIR" ]]; then echo 'Installer directory is linked. Preserve it for review.'; exit 1; fi
if [[ ! -e "$INSTALLER_DIR" ]]; then
  mkdir -p "$(dirname "$INSTALLER_DIR")"
  if [[ -n "$INSTALLER_COMMIT" ]]; then
    mkdir "$INSTALLER_DIR"
    git -C "$INSTALLER_DIR" init --quiet
    git -C "$INSTALLER_DIR" remote add origin https://github.com/aibuild-lab/aibl-installer.git
    git -C "$INSTALLER_DIR" fetch --depth 1 origin "$INSTALLER_COMMIT"
    git -C "$INSTALLER_DIR" checkout --detach --quiet FETCH_HEAD
  else
    git clone --depth 1 https://github.com/aibuild-lab/aibl-installer.git "$INSTALLER_DIR"
  fi
fi
if [[ ! -d "$INSTALLER_DIR/.git" || -L "$INSTALLER_DIR/.git" || "$(git -C "$INSTALLER_DIR" remote get-url origin)" != https://github.com/aibuild-lab/aibl-installer.git ]]; then echo 'Installer path is occupied by another project. Preserve it for review.'; exit 1; fi
INSTALLER_CHANGES="$(git -C "$INSTALLER_DIR" status --porcelain)"
if [[ -n "$INSTALLER_CHANGES" ]]; then echo 'Installer has local work. Preserve it for review; no update was applied.'; exit 1; fi
if [[ -n "$INSTALLER_COMMIT" && "$(git -C "$INSTALLER_DIR" rev-parse HEAD)" != "$INSTALLER_COMMIT" ]]; then echo 'Frozen installer revision differs. Preserve it for review.'; exit 1; fi
if [[ ! -f "$INSTALLER_DIR/scripts/enroll.py" ]]; then echo 'Retained installer predates enrollment. Ask for the reviewed installer update; no files were replaced.'; exit 1; fi
if [[ -n "$INSTALLER_COMMIT" ]]; then exec "$PYTHON" "$INSTALLER_DIR/scripts/course_setup.py" --course "$COURSE" --harness "$HARNESS" --distribution-lock "$DISTRIBUTION_LOCK" --distribution-sha256 "$DISTRIBUTION_SHA256"; fi
if [[ -n "$COURSE" ]]; then exec "$PYTHON" "$INSTALLER_DIR/scripts/course_setup.py" --course "$COURSE" --harness "$HARNESS"; fi
exec "$PYTHON" "$INSTALLER_DIR/scripts/course_setup.py" --course agent-essentials --harness "$HARNESS"
