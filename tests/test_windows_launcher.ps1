$ErrorActionPreference = 'Stop'
$Launcher = Join-Path (Split-Path $PSScriptRoot -Parent) 'start.ps1'
$Tokens = $null
$ParseErrors = $null
$Ast = [System.Management.Automation.Language.Parser]::ParseFile($Launcher,[ref]$Tokens,[ref]$ParseErrors)
if ($ParseErrors.Count) { throw ($ParseErrors | Out-String) }
$Definition = $Ast.Find({ param($Node) $Node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $Node.Name -eq 'Find-CompatiblePython' },$true)
if (-not $Definition) { throw 'Python resolver function missing' }
. ([scriptblock]::Create($Definition.Extent.Text))
$ResolvedPython = Find-CompatiblePython
if (-not $ResolvedPython) { throw 'This test host needs Python 3.11 or newer to verify interpreter resolution' }
& $ResolvedPython -c 'import sys; assert sys.version_info >= (3,11)'
if ($LASTEXITCODE -ne 0) { throw 'Resolved interpreter does not satisfy the course floor' }
Write-Output 'PowerShell parse and actual interpreter-resolution checks passed. OS installs, execution policy and Windows onboarding remain separate tests.'
