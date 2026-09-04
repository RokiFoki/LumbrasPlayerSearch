@echo off
setlocal enableextensions

rem Chrome speaks the native-messaging protocol over this process's stdin and
rem stdout, so nothing here may write to stdout. Diagnostics go to stderr only.
rem The host script always sits next to this launcher.

set "HOST=%~dp0host.py"

rem Prefer the py launcher pinned to Python 3, which cannot resolve to a 2.x
rem interpreter. The probe's own output is discarded so it never reaches stdout.
py -3 -c "import sys" 1>nul 2>nul
if not errorlevel 1 goto :use_py

rem Fall back to python on PATH, but confirm it really is Python 3.
python -c "import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)" 1>nul 2>nul
if not errorlevel 1 goto :use_python

echo Lumbras ^& Chess Genie native host: Python 3 was not found on PATH. 1>&2
echo Install Python 3 from https://www.python.org/downloads/windows/ and reopen Chrome. 1>&2
exit /b 9009

:use_py
py -3 "%HOST%" %*
exit /b %ERRORLEVEL%

:use_python
python "%HOST%" %*
exit /b %ERRORLEVEL%
