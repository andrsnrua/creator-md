@echo off
set "CREATOR_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%CREATOR_PY%" (
  start "" "%CREATOR_PY%" -B "%~dp0run.py"
) else (
  start "" pythonw -B "%~dp0run.py"
)
