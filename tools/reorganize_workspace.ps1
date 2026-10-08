$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$sourceRoot = Join-Path $workspace 'POWERNEXT'
$records = [Collections.Generic.List[object]]::new()
function Safe-Move([string]$oldRelative,[string]$newRelative) {
    $oldPath = [IO.Path]::GetFullPath((Join-Path $workspace $oldRelative))
    $newPath = [IO.Path]::GetFullPath((Join-Path $workspace $newRelative))
    foreach($path in @($oldPath,$newPath)) {
        if(-not $path.StartsWith($workspace+'\',[StringComparison]::OrdinalIgnoreCase)) {throw "Outside workspace: $path"}
    }
    if(-not (Test-Path -LiteralPath $oldPath)) {throw "Missing source: $oldPath"}
    if(Test-Path -LiteralPath $newPath) {throw "Destination exists: $newPath"}
    $item = Get-Item -LiteralPath $oldPath -Force
    if($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {throw "Reparse point: $oldPath"}
    if($item.PSIsContainer) {
        $unsafe = Get-ChildItem -LiteralPath $oldPath -Force -Recurse | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } | Select-Object -First 1
        if($unsafe) {throw "Nested reparse point: $($unsafe.FullName)"}
    }
    $parent = Split-Path -Parent $newPath
    [IO.Directory]::CreateDirectory($parent) | Out-Null
    Move-Item -LiteralPath $oldPath -Destination $newPath
    $records.Add([pscustomobject]@{from=$oldRelative;to=$newRelative;kind=if($item.PSIsContainer){'directory'}else{'file'}})
    Write-Host "Archived/moved $oldRelative"
    $records | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $sourceRoot 'evidence\integration\reorganization.json') -Encoding utf8
}
$primary=@('HV IG Problem Statement.pdf','Parameter values ivg.docx','Hybrid_Physics_ML_Impulse_Generator_Optimiser.xlsx','questions.txt','clarifications.txt','briefing.txt','PowerNext_Track1_PRD.docx')
$primaryManifest = foreach($name in $primary) {
    $path=Join-Path $workspace $name
    [pscustomobject]@{original_path=$name;new_path=('sources/original/'+$name);bytes=(Get-Item -LiteralPath $path).Length;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
[IO.Directory]::CreateDirectory((Join-Path $workspace 'sources')) | Out-Null
$primaryManifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $workspace 'sources\ORIGINAL_SOURCE_MANIFEST.json') -Encoding utf8
foreach($name in $primary) { Safe-Move $name ('sources\original\'+$name) }
foreach($name in @('_ui_redesign_backup','PowerNext_Application_Package','PowerNext_CPRI_Revalidation_2026-10-04','PowerNext_ML_Package','PowerNext_Optimizer_Package','PowerNext_Physics_Package','PowerNext_Track1_Final','RedTeam_2026-10-03','release_tools')) { Safe-Move $name ('archive\'+$name) }
Safe-Move 'PowerNext_Training_Docs' 'documentation\training'
foreach($name in @('PowerNext_Application_Preview.jpg','PowerNext_Final_Preview.png')) {Safe-Move $name ('archive\previews\'+$name)}
foreach($name in @('PowerNext_Track1_Application_Package_UI_0.2.0.receipt.json','PowerNext_Track1_Application_Package_UI_0.2.0.smoke.json','PowerNext_Track1_Application_Package_UI_0.2.0.zip','PowerNext_Track1_Application_Package.receipt.json','PowerNext_Track1_Application_Package.smoke.json','PowerNext_Track1_Application_Package.zip','PowerNext_Track1_Final.receipt.json','PowerNext_Track1_Final.zip','PowerNext_Track1_Final.zip.sha256','PowerNext_Track1_ML_Engineering_Package.receipt.json','PowerNext_Track1_ML_Engineering_Package.zip','PowerNext_Track1_Optimizer_Engineering_Package.receipt.json','PowerNext_Track1_Optimizer_Engineering_Package.zip','PowerNext_Track1_Physics_Engineering_Package.zip')) {Safe-Move $name ('archive\packages\'+$name)}
foreach($name in @('CPRI_CLARIFICATION_IMPACT_REPORT.md','FINAL_CLAIMS_AND_LIMITATIONS.md','FINAL_COMPETITION_READINESS.md','FINAL_REGRESSION_REPORT.md','FINAL_RELEASE_NOTES.md','PHASE_1_PHYSICS_UPDATE_REPORT.md','PHASE_2_ML_RETRAIN_REPORT.md','PHASE_3_OPTIMIZER_UPDATE_REPORT.md','PHASE_4_APPLICATION_UPDATE_REPORT.md','UPDATED_JUDGE_QA.md')) {Safe-Move ('POWERNEXT\docs\'+$name) ('POWERNEXT\docs\archive\2026-10-04\'+$name)}
Safe-Move 'POWERNEXT\release' 'POWERNEXT\archive\release-2026-10-04'
Safe-Move 'POWERNEXT\models' 'POWERNEXT\archive\model-mirror-2026-10-04'
Safe-Move 'POWERNEXT\FINAL_FILE_MANIFEST.json' 'POWERNEXT\archive\release-2026-10-04\SOURCE_FILE_MANIFEST.json'
Safe-Move 'POWERNEXT\RELEASE_METADATA.json' 'POWERNEXT\archive\release-2026-10-04\SOURCE_RELEASE_METADATA.json'
foreach($name in @('integrate_ui.py','refine_ui.py','finish_presentation.py')) {Safe-Move ('POWERNEXT\tools\'+$name) ('POWERNEXT\archive\integration-edit-scripts\'+$name)}
foreach($row in $primaryManifest) {
    $path=Join-Path $workspace $row.new_path
    if((Get-Item -LiteralPath $path).Length -ne $row.bytes -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $row.sha256) {throw "Source preservation failed: $path"}
}
Write-Host 'PASS: every original source preserved byte-for-byte; no files deleted.'
