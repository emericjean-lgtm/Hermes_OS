# Recompiles the Desktop launcher (HermesOSLauncher.cs) into an .exe.
# Run from anywhere; paths are relative to this script's own location.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$csc = Get-ChildItem "C:\Windows\Microsoft.NET\Framework64" -Recurse -Filter csc.exe -ErrorAction Stop |
    Select-Object -Last 1 -ExpandProperty FullName
$src = Join-Path $here "HermesOSLauncher.cs"
$out = Join-Path ([Environment]::GetFolderPath("Desktop")) "Hermes OS.exe"

& $csc /nologo /target:exe /out:"$out" "$src"
if (Test-Path $out) {
    Write-Output "OK: $out"
} else {
    Write-Error "Build failed"
}
