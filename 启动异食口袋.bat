@echo off
cd /d "%~dp0"
py -3 leftover_pet.py
if errorlevel 1 python leftover_pet.py
