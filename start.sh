#!/bin/bash
# Shared macOS course entry. Existing workshop implementation remains separate.
set -euo pipefail
export AIBL_BOOTSTRAP_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
COURSE="${1:-}"
DISTRIBUTION_LOCK="${2:-}"
DISTRIBUTION_SHA256="${3:-}"
INSTALLER_COMMIT="${4:-}"
LAUNCHER_SHA256="${5:-}"
if [[ -n "$DISTRIBUTION_LOCK$DISTRIBUTION_SHA256$INSTALLER_COMMIT$LAUNCHER_SHA256" ]]; then
  if [[ "$COURSE" != agent-native-workforce || ! -f "$DISTRIBUTION_LOCK" || ! "$DISTRIBUTION_SHA256" =~ ^[a-f0-9]{64}$ || ! "$INSTALLER_COMMIT" =~ ^[a-f0-9]{40}$ || ! "$LAUNCHER_SHA256" =~ ^[a-f0-9]{64}$ ]]; then echo 'Pinned setup needs the course, reviewed lock file, lock digest, installer commit and launcher digest.'; exit 1; fi
  if [[ "$(shasum -a 256 "$AIBL_BOOTSTRAP_PATH" | cut -d' ' -f1)" != "$LAUNCHER_SHA256" || "$(shasum -a 256 "$DISTRIBUTION_LOCK" | cut -d' ' -f1)" != "$DISTRIBUTION_SHA256" ]]; then echo 'Pinned launcher or distribution lock bytes differ. Download the reviewed files again.'; exit 1; fi
  DISTRIBUTION_LOCK="$(cd "$(dirname "$DISTRIBUTION_LOCK")" && pwd)/$(basename "$DISTRIBUTION_LOCK")"
fi
if [[ -z "$COURSE" ]]; then
  echo 'Which class are you joining?'
  echo '1. Agent Essentials'
  echo '2. Agent Native Workforce (includes Essentials)'
  echo '3. Existing Agent Native OS workshop'
  read -r -p 'Choose 1, 2 or 3: ' choice
  case "$choice" in 1) COURSE=agent-essentials;; 2) COURSE=agent-native-workforce;; 3) COURSE=legacy-workshop;; *) echo 'Rerun and choose a listed course.'; exit 1;; esac
fi
case "$COURSE" in agent-essentials|agent-native-workforce|legacy-workshop) ;; *) echo 'Unknown course.'; exit 1;; esac
if [[ "$(uname -s)" != Darwin ]]; then echo 'Use start.ps1 on native Windows. This entry supports macOS.'; exit 1; fi
if [[ "$(sw_vers -productVersion | cut -d. -f1)" -lt 13 ]]; then echo 'macOS 13 or later is required.'; exit 1; fi
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! git --version >/dev/null 2>&1 || ! command -v gh >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3,11))' >/dev/null 2>&1; then
 if ! command -v brew >/dev/null 2>&1; then
  echo 'Homebrew installs missing prerequisites. Its official installer may ask for macOS consent.'
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
 fi
fi
if ! git --version >/dev/null 2>&1; then brew install git; fi
if ! command -v gh >/dev/null 2>&1; then brew install gh; fi
PYTHON=python3
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3,11))' >/dev/null 2>&1; then
 brew install python@3.13
 PYTHON="$(brew --prefix python@3.13)/bin/python3.13"
fi
if ! command -v claude >/dev/null 2>&1; then
  curl -fsSL https://claude.ai/install.sh -o "${TMPDIR:-/tmp}/aibl-claude-install.sh"
  bash "${TMPDIR:-/tmp}/aibl-claude-install.sh"
fi
INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "$INSTALLER_COMMIT" ]]; then
  INSTALLER_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aibl-pinned-installer.XXXXXX")"
  git -C "$INSTALLER_DIR" init --quiet
  git -C "$INSTALLER_DIR" remote add origin https://github.com/aibuild-lab/workshop-installer.git
  git -C "$INSTALLER_DIR" fetch --depth 1 origin "$INSTALLER_COMMIT"
  git -C "$INSTALLER_DIR" checkout --detach --quiet FETCH_HEAD
  if [[ "$(git -C "$INSTALLER_DIR" rev-parse HEAD)" != "$INSTALLER_COMMIT" ]]; then echo 'Frozen installer revision was not fetched.'; exit 1; fi
elif [[ ! -f "$INSTALLER_DIR/course-options.json" ]]; then
  INSTALLER_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aibl-course-installer.XXXXXX")"
  git clone --depth 1 https://github.com/aibuild-lab/workshop-installer.git "$INSTALLER_DIR"
fi
if [[ "$COURSE" == legacy-workshop ]]; then exec bash "$INSTALLER_DIR/install.sh"; fi
if [[ -n "$INSTALLER_COMMIT" ]]; then exec "$PYTHON" "$INSTALLER_DIR/scripts/course_setup.py" --course "$COURSE" --distribution-lock "$DISTRIBUTION_LOCK" --distribution-sha256 "$DISTRIBUTION_SHA256"; fi
exec "$PYTHON" "$INSTALLER_DIR/scripts/course_setup.py" --course "$COURSE"
