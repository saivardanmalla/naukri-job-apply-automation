@echo off
title Naukri Job Apply Bot
cd /d "%~dp0"
start powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0run.ps1"
