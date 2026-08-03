param([switch]$Clean)
$ErrorActionPreference = "Stop"
if ($Clean) {
    Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
}
py -3 -m PyInstaller --noconfirm --clean --windowed --name "余食" --icon "assets\tray-icon.ico" --add-data "assets;assets" --collect-all tkinterdnd2 leftover_pet.py
Write-Host "Built: dist\余食\余食.exe"
