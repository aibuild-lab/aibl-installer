param([string]$Course = "", [string]$DistributionLock = "", [string]$DistributionSHA256 = "", [string]$InstallerCommit = "", [string]$LauncherSHA256 = "", [ValidateSet('claude','codex')][string]$Harness = 'claude')
$ErrorActionPreference = 'Stop'
$env:AIBL_BOOTSTRAP_PATH = $PSCommandPath
if ($DistributionLock -or $DistributionSHA256 -or $InstallerCommit -or $LauncherSHA256) {
  if ($Course -ne 'agent-workforce' -or -not (Test-Path -LiteralPath $DistributionLock -PathType Leaf) -or $DistributionSHA256 -cnotmatch '^[a-f0-9]{64}$' -or $InstallerCommit -cnotmatch '^[a-f0-9]{40}$' -or $LauncherSHA256 -cnotmatch '^[a-f0-9]{64}$') { throw 'Pinned setup needs the course, reviewed lock file, lock digest, installer commit and launcher digest.' }
  if ((Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $LauncherSHA256 -or (Get-FileHash -LiteralPath $DistributionLock -Algorithm SHA256).Hash.ToLowerInvariant() -ne $DistributionSHA256) { throw 'Pinned launcher or distribution lock bytes differ. Download the reviewed files again.' }
  $DistributionLock = (Resolve-Path -LiteralPath $DistributionLock).Path
}
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Use start.sh on macOS. This launcher requires native Windows.' }
# The installer builds the Essentials hub for everyone; programs join the workbench later through scripts\enroll.py. An explicit -Course is kept for pinned cohort setups.
function Refresh-ProcessPath {
  $env:Path = $env:Path + ';' + [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User') + ';' + (Join-Path $HOME '.local\bin')
}
function Find-CompatiblePython {
  foreach ($Probe in @(@('py','-3'),@('python'),@('python3'))) {
    $Executable = $Probe[0]
    if (Get-Command $Executable -ErrorAction SilentlyContinue) {
      $PrefixArguments = @($Probe | Select-Object -Skip 1)
      $PythonLocation = & $Executable @PrefixArguments -c 'import sys; assert sys.version_info >= (3,11); print(sys.executable)' 2>$null
      if ($LASTEXITCODE -eq 0 -and $PythonLocation) {
        return [string]($PythonLocation | Select-Object -Last 1)
      }
    }
  }
  return $null
}
function Install-Missing([string]$Command, [string]$Package) {
  if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install or update Microsoft App Installer from the Microsoft Store, then rerun this launcher.' }
    winget install --id $Package --exact --source winget
    if ($LASTEXITCODE -ne 0) { throw "Installation paused for $Package. Complete visible consent and rerun." }
    Refresh-ProcessPath
  }
}
Refresh-ProcessPath
Install-Missing 'git' 'Git.Git'
Install-Missing 'gh' 'GitHub.cli'
Install-Missing 'node' 'OpenJS.NodeJS.LTS'
$Python = Find-CompatiblePython
if (-not $Python) {
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install Microsoft App Installer, then rerun.' }
  winget install --id Python.Python.3.13 --exact --source winget
  if ($LASTEXITCODE -ne 0) { throw 'Python installation paused. Complete consent and rerun.' }
  Refresh-ProcessPath
  $Python = Find-CompatiblePython
  if (-not $Python) { throw 'Open a fresh PowerShell window and rerun so the installed Python is visible.' }
}
if ($Harness -eq 'claude' -and -not (Get-Command claude -ErrorAction SilentlyContinue)) {
  $ClaudeInstaller = Join-Path ([IO.Path]::GetTempPath()) 'aibl-claude-install.ps1'
  Invoke-WebRequest 'https://claude.ai/install.ps1' -OutFile $ClaudeInstaller
  & $ClaudeInstaller
  Refresh-ProcessPath
}
if ($Harness -eq 'codex' -and -not (Get-Command codex -ErrorAction SilentlyContinue)) {
  $CodexInstaller = Join-Path ([IO.Path]::GetTempPath()) 'aibl-codex-install.ps1'
  Invoke-WebRequest 'https://chatgpt.com/codex/install.ps1' -OutFile $CodexInstaller
  & $CodexInstaller
  $env:Path = $env:Path + ';' + (Join-Path $HOME '.codex\bin')
  Refresh-ProcessPath
}
# Retain the engine. Do not reset, pull or replace an existing checkout.
$InstallerDir = Join-Path $HOME 'GitHub/aibl-installer'
if ($InstallerCommit) { $InstallerDir = Join-Path $HOME ('.aibl/installers/' + $InstallerCommit) }
if (Test-Path -LiteralPath $InstallerDir) {
  if ((Get-Item -LiteralPath $InstallerDir).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Installer directory is linked. Preserve it for review.' }
} else {
  New-Item -ItemType Directory -Force -Path (Split-Path $InstallerDir) | Out-Null
  if ($InstallerCommit) {
    New-Item -ItemType Directory -Path $InstallerDir | Out-Null
    git -C $InstallerDir init --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Installer initialization failed.' }
    git -C $InstallerDir remote add origin https://github.com/aibuild-lab/aibl-installer.git
    if ($LASTEXITCODE -ne 0) { throw 'Installer origin could not be set.' }
    git -C $InstallerDir fetch --depth 1 origin $InstallerCommit
    if ($LASTEXITCODE -ne 0) { throw 'Frozen installer download failed. Preserve this interrupted directory for recovery.' }
    git -C $InstallerDir checkout --detach --quiet FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Frozen installer checkout failed.' }
  } else {
    git clone --depth 1 https://github.com/aibuild-lab/aibl-installer.git $InstallerDir
    if ($LASTEXITCODE -ne 0) { throw 'Download failed. Preserve this interrupted directory for recovery.' }
  }
}
$GitDir = Join-Path $InstallerDir '.git'
if (-not (Test-Path -LiteralPath $GitDir -PathType Container)) { throw 'Installer path is occupied by another project. Preserve it for review.' }
if ((Get-Item -LiteralPath $GitDir).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Installer Git metadata is linked. Preserve it for review.' }
$InstallerOrigin = git -C $InstallerDir remote get-url origin
if ($LASTEXITCODE -ne 0 -or $InstallerOrigin -ne 'https://github.com/aibuild-lab/aibl-installer.git') { throw 'Installer origin differs. Preserve it for review.' }
$InstallerChanges = git -C $InstallerDir status --porcelain
if ($LASTEXITCODE -ne 0 -or $InstallerChanges) { throw 'Installer has local work. Preserve it for review; no update was applied.' }
if ($InstallerCommit) {
  $ObservedInstallerCommit = git -C $InstallerDir rev-parse HEAD
  if ($LASTEXITCODE -ne 0 -or $ObservedInstallerCommit -ne $InstallerCommit) { throw 'Frozen installer revision differs. Preserve it for review.' }
}
if (-not (Test-Path (Join-Path $InstallerDir 'scripts/enroll.py') -PathType Leaf)) { throw 'Retained installer predates enrollment. Ask for the reviewed installer update; no files were replaced.' }
if ($InstallerCommit) {
  & $Python (Join-Path $InstallerDir 'scripts\course_setup.py') --course $Course --harness $Harness --distribution-lock $DistributionLock --distribution-sha256 $DistributionSHA256
  exit $LASTEXITCODE
}
if ($Course) { & $Python (Join-Path $InstallerDir 'scripts\course_setup.py') --course $Course --harness $Harness; exit $LASTEXITCODE }
& $Python (Join-Path $InstallerDir 'scripts\course_setup.py') --course agent-essentials --harness $Harness
exit $LASTEXITCODE
