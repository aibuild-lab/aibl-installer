#!/bin/bash
# Shared macOS course entry. Existing workshop implementation remains separate.
set -euo pipefail
COURSE="${1:-}"
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
if [[ ! -f "$INSTALLER_DIR/course-options.json" ]]; then
  INSTALLER_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aibl-course-installer.XXXXXX")"
  git clone --depth 1 https://github.com/aibuild-lab/workshop-installer.git "$INSTALLER_DIR"
fi
if [[ "$COURSE" == legacy-workshop ]]; then exec bash "$INSTALLER_DIR/install.sh"; fi
exec "$PYTHON" "$INSTALLER_DIR/scripts/course_setup.py" --course "$COURSE"
