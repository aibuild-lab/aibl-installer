param([string]$Course = "")
$ErrorActionPreference = 'Stop'
if (-not $Course) {
  Write-Host 'Which class are you joining?'
  Write-Host '1. Agent Essentials'
  Write-Host '2. Agent Native Workforce (includes Essentials)'
  Write-Host '3. Existing Agent Native OS workshop'
  switch (Read-Host 'Choose 1, 2 or 3') {
    '1' { $Course = 'agent-essentials' }
    '2' { $Course = 'agent-native-workforce' }
    '3' { $Course = 'legacy-workshop' }
    default { throw 'Rerun and choose a listed course.' }
  }
}
if ($Course -notin @('agent-essentials','agent-native-workforce','legacy-workshop')) { throw 'Unknown course.' }
function Refresh-ProcessPath {
  $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User') + ';' + (Join-Path $HOME '.local\bin')
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
$Python = $null
foreach ($Candidate in @('python','python3')) {
  if (Get-Command $Candidate -ErrorAction SilentlyContinue) {
    & $Candidate -c 'import sys; sys.exit(sys.version_info < (3,11))' 2>$null
    if ($LASTEXITCODE -eq 0) { $Python = $Candidate; break }
  }
}
if (-not $Python) {
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install Microsoft App Installer, then rerun.' }
  winget install --id Python.Python.3.13 --exact --source winget
  if ($LASTEXITCODE -ne 0) { throw 'Python installation paused. Complete consent and rerun.' }
  Refresh-ProcessPath
  $Python = 'python'
  & $Python -c 'import sys; sys.exit(sys.version_info < (3,11))'
  if ($LASTEXITCODE -ne 0) { throw 'Open a fresh PowerShell window and rerun so the installed Python is visible.' }
}
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
  $ClaudeInstaller = Join-Path ([IO.Path]::GetTempPath()) 'aibl-claude-install.ps1'
  Invoke-WebRequest 'https://claude.ai/install.ps1' -OutFile $ClaudeInstaller
  & $ClaudeInstaller
  Refresh-ProcessPath
}
$InstallerDir = $PSScriptRoot
if (-not (Test-Path (Join-Path $InstallerDir 'course-options.json'))) {
  $InstallerDir = Join-Path ([IO.Path]::GetTempPath()) ('aibl-course-installer-' + [guid]::NewGuid().ToString('N'))
  git clone --depth 1 https://github.com/aibuild-lab/workshop-installer.git $InstallerDir
  if ($LASTEXITCODE -ne 0) { throw 'Download failed. Rerun when GitHub is reachable.' }
}
if ($Course -eq 'legacy-workshop') { & (Join-Path $InstallerDir 'install.ps1'); exit $LASTEXITCODE }
& $Python (Join-Path $InstallerDir 'scripts\course_setup.py') --course $Course
exit $LASTEXITCODE
