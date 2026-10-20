# Adds the folder of this script (where ffpy.exe is) to the current user's PATH,
# so that "ffpy water.inp" works in any new terminal.
#   powershell -ExecutionPolicy Bypass -File add_to_path.ps1
$dir = $PSScriptRoot
$path = [Environment]::GetEnvironmentVariable("Path", "User")
# @() keeps a one-entry PATH an array; otherwise "+" below would glue strings
# together without the ";" separator.
$parts = @()
if ($path) { $parts = @($path.Split(";") | Where-Object { $_ }) }
if ($parts -contains $dir) {
    Write-Host "already in PATH: $dir"
} else {
    $parts = @($parts) + @($dir)
    [Environment]::SetEnvironmentVariable("Path", ($parts -join ";"), "User")
    Write-Host "added to the user PATH: $dir"
    Write-Host "open a new terminal and run: ffpy --version"
}
