@echo off
call "%~dp0..\launch.cmd" sensors
if errorlevel 1 pause
