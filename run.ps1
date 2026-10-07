param([int]$Port=8765, [switch]$NoBrowser)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$launchArgs=@('-m','powernext_app','--port',"$Port")
if ($NoBrowser) { $launchArgs += '--no-browser' }
& (Join-Path $PSScriptRoot 'runtime\python.exe') @launchArgs
exit $LASTEXITCODE
