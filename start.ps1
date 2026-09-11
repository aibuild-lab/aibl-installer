param([string]$Course = "", [string]$DistributionLock = "", [string]$DistributionSHA256 = "", [string]$InstallerCommit = "", [string]$LauncherSHA256 = "")
$ErrorActionPreference = 'Stop'
$env:AIBL_BOOTSTRAP_PATH = $PSCommandPath
if ($DistributionLock -or $DistributionSHA256 -or $InstallerCommit -or $LauncherSHA256) {
  if ($Course -ne 'agent-workforce' -or -not (Test-Path -LiteralPath $DistributionLock -PathType Leaf) -or $DistributionSHA256 -cnotmatch '^[a-f0-9]{64}$' -or $InstallerCommit -cnotmatch '^[a-f0-9]{40}$' -or $LauncherSHA256 -cnotmatch '^[a-f0-9]{64}$') { throw 'Pinned setup needs the course, reviewed lock file, lock digest, installer commit and launcher digest.' }
  if ((Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $LauncherSHA256 -or (Get-FileHash -LiteralPath $DistributionLock -Algorithm SHA256).Hash.ToLowerInvariant() -ne $DistributionSHA256) { throw 'Pinned launcher or distribution lock bytes differ. Download the reviewed files again.' }
  $DistributionLock = (Resolve-Path -LiteralPath $DistributionLock).Path
}
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Use start.sh on macOS. This launcher requires native Windows.' }
# The program menu lives in course-options.json and is asked by scripts\course_setup.py once the tools are ready.
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
$Python = Find-CompatiblePython
if (-not $Python) {
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install Microsoft App Installer, then rerun.' }
  winget install --id Python.Python.3.13 --exact --source winget
  if ($LASTEXITCODE -ne 0) { throw 'Python installation paused. Complete consent and rerun.' }
  Refresh-ProcessPath
  $Python = Find-CompatiblePython
  if (-not $Python) { throw 'Open a fresh PowerShell window and rerun so the installed Python is visible.' }
}
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
  $ClaudeInstaller = Join-Path ([IO.Path]::GetTempPath()) 'aibl-claude-install.ps1'
  Invoke-WebRequest 'https://claude.ai/install.ps1' -OutFile $ClaudeInstaller
  & $ClaudeInstaller
  Refresh-ProcessPath
}
$InstallerDir = $PSScriptRoot
if ($InstallerCommit) {
  $InstallerDir = Join-Path ([IO.Path]::GetTempPath()) ('aibl-pinned-installer-' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $InstallerDir | Out-Null
  git -C $InstallerDir init --quiet
  if ($LASTEXITCODE -ne 0) { throw 'Pinned installer directory could not be initialized.' }
  git -C $InstallerDir remote add origin https://github.com/aibuild-lab/aibl-installer.git
  if ($LASTEXITCODE -ne 0) { throw 'Pinned installer origin could not be set.' }
  git -C $InstallerDir fetch --depth 1 origin $InstallerCommit
  if ($LASTEXITCODE -ne 0) { throw 'Frozen installer download failed. Rerun when GitHub is reachable.' }
  git -C $InstallerDir checkout --detach --quiet FETCH_HEAD
  if ($LASTEXITCODE -ne 0) { throw 'Frozen installer checkout failed.' }
  $ObservedInstallerCommit = git -C $InstallerDir rev-parse HEAD
  if ($LASTEXITCODE -ne 0 -or $ObservedInstallerCommit -ne $InstallerCommit) { throw 'Frozen installer revision was not fetched.' }
} elseif (-not (Test-Path (Join-Path $InstallerDir 'course-options.json'))) {
  $InstallerDir = Join-Path ([IO.Path]::GetTempPath()) ('aibl-course-installer-' + [guid]::NewGuid().ToString('N'))
  git clone --depth 1 https://github.com/aibuild-lab/aibl-installer.git $InstallerDir
  if ($LASTEXITCODE -ne 0) { throw 'Download failed. Rerun when GitHub is reachable.' }
}
if ($InstallerCommit) {
  & $Python (Join-Path $InstallerDir 'scripts\course_setup.py') --course $Course --distribution-lock $DistributionLock --distribution-sha256 $DistributionSHA256
  exit $LASTEXITCODE
}
if ($Course) { & $Python (Join-Path $InstallerDir 'scripts\course_setup.py') --course $Course; exit $LASTEXITCODE }
& $Python (Join-Path $InstallerDir 'scripts\course_setup.py')
exit $LASTEXITCODE
