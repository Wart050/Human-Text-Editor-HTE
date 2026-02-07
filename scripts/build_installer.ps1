$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    Write-Host "Building EXE..."
    python .\build_exe.py

    Write-Host "Building installer..."
    $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        $candidates = @(
            "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            "C:\Program Files\Inno Setup 6\ISCC.exe"
        )
        foreach ($c in $candidates) {
            if (Test-Path $c) { $iscc = $c; break }
        }
    }
    if (-not $iscc) {
        throw "Inno Setup compiler (ISCC.exe) not found. Install Inno Setup 6 and retry."
    }
    & $iscc ".\installer\HumanTextEditor.iss"
    Write-Host "Installer created in .\dist\installer"
}
finally {
    Pop-Location
}
