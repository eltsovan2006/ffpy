# Builds dist\ffpy\ffpy.exe and dist\ffpy-<version>-win64.zip.
# Usage (from the repository root):
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-EnvPath C:\path\to\conda\env]
param(
    [string]$EnvPath = "$env:USERPROFILE\miniforge3\envs\ffpy"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$EnvPath\python.exe")) {
    throw "conda env not found at $EnvPath. Create it with: conda env create -f environment.yml"
}
# Same PATH as 'conda activate', so PyInstaller finds the DLLs of libcint/libxc/OpenBLAS.
$env:PATH = "$EnvPath;$EnvPath\Library\mingw-w64\bin;$EnvPath\Library\usr\bin;$EnvPath\Library\bin;$EnvPath\Scripts;$env:PATH"

Push-Location $root
try {
    $version = & "$EnvPath\python.exe" -c "import ffpy; print(ffpy.__version__)"
    & "$EnvPath\python.exe" -m PyInstaller --noconfirm --clean `
        --distpath "$root\dist" --workpath "$root\build" "$root\packaging\ffpy.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

    $dist = "$root\dist\ffpy"
    Copy-Item -Recurse -Force "$root\examples" "$dist\examples"
    Copy-Item -Force "$root\README.md", "$root\THIRD_PARTY_NOTICES.md" $dist
    Copy-Item -Force "$root\docs\KEYWORDS.md" $dist
    Copy-Item -Force "$root\packaging\add_to_path.ps1" $dist

    # smoke test of the frozen build on every example, without the conda env on PATH
    $tmp = Join-Path $env:TEMP "ffpy_smoke"
    New-Item -ItemType Directory -Force $tmp | Out-Null
    $savedPath = $env:PATH
    $env:PATH = ($env:PATH.Split(";") | Where-Object { $_ -notlike "$EnvPath*" }) -join ";"
    try {
        foreach ($inp in Get-ChildItem "$root\examples\*.inp") {
            & "$dist\ffpy.exe" $inp.FullName -o $tmp -q
            if ($LASTEXITCODE -ne 0) { throw "frozen ffpy.exe failed on $($inp.Name) (code $LASTEXITCODE)" }
            Write-Host ("{0,-24} {1}" -f $inp.Name, (Get-Content (Join-Path $tmp ($inp.BaseName + ".out")) -Tail 1))
        }
    } finally {
        $env:PATH = $savedPath
    }

    $zip = "$root\dist\ffpy-$version-win64.zip"
    if (Test-Path $zip) { Remove-Item $zip }
    Compress-Archive -Path $dist -DestinationPath $zip
    Write-Host "built $zip"
} finally {
    Pop-Location
}
