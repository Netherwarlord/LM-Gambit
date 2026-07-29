@echo off
setlocal enabledelayedexpansion
rem LM-Gambit launcher (Windows).
rem
rem First run creates a virtual environment beside this script and installs the
rem dependencies into it; later runs skip straight to starting the app.
rem
rem The environment is built on YOUR machine rather than shipped prebuilt, and
rem that is the whole point: llama-cpp-python is a compiled package whose GPU
rem support is baked in at install time. A prebuilt bundle would freeze one
rem choice -- almost certainly CPU-only -- for everybody. Installing here means
rem pip picks the build that matches this machine.
rem
rem For NVIDIA or AMD GPU acceleration, see GPU-ACCELERATION.md.

cd /d "%~dp0"
set "VENV=%~dp0.venv"

if exist "%VENV%\Scripts\python.exe" goto :run

echo First run - setting up. This takes a few minutes and happens once.
echo.

rem The Windows launcher is the reliable way to pick a version; fall back to
rem whatever "python" resolves to, which may be the Microsoft Store stub.
set "PY_CMD="
for %%V in (3.13 3.12 3.11 3.10) do (
    if not defined PY_CMD (
        py -%%V -c "import sys" >nul 2>&1 && set "PY_CMD=py -%%V"
    )
)
if not defined PY_CMD (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo No suitable Python found.
    echo.
    echo LM-Gambit needs Python 3.10 or newer.
    echo   Download: https://www.python.org/downloads/
    echo   Tick "Add python.exe to PATH" during installation.
    echo.
    echo If you see a Microsoft Store window when typing "python", that is a
    echo placeholder rather than a real install - use the link above.
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%V in ('%PY_CMD% --version 2^>^&1') do echo Using %%V

%PY_CMD% -m venv "%VENV%"
if errorlevel 1 (
    echo.
    echo Could not create a virtual environment.
    echo.
    pause
    exit /b 1
)

echo Installing dependencies...
"%VENV%\Scripts\python.exe" -m pip install --quiet --upgrade pip

rem llama-cpp-python ships only an sdist to PyPI, so a plain install compiles
rem it from source. On Windows that needs nmake and cl.exe on PATH, and those
rem exist only inside a Visual Studio developer shell -- which nobody
rem double-clicking a launcher is in. Installing Build Tools does NOT put them
rem on the system PATH, so the compile fails identically afterwards.
rem
rem The upstream index below carries prebuilt win_amd64 wheels, so the normal
rem case never compiles at all. It is the same index GPU-ACCELERATION.md uses
rem for the CUDA builds.
"%VENV%\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt" --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
if errorlevel 1 (
    echo.
    echo Dependency installation failed.
    echo.
    echo If the error above mentions llama-cpp-python, nmake, or
    echo CMAKE_C_COMPILER, then pip could not find a prebuilt wheel and fell
    echo back to compiling from source.
    echo.
    echo Note that installing Visual Studio Build Tools is not enough on its
    echo own - it does not add the compiler to your PATH. You have to start
    echo this launcher from a developer shell instead:
    echo.
    echo   Start menu -^> "x64 Native Tools Command Prompt for VS 2022"
    echo   cd /d "%~dp0"
    echo   LM-Gambit.bat
    echo.
    echo Build Tools, if you do not have them:
    echo   https://visualstudio.microsoft.com/visual-cpp-build-tools/
    echo   ^(select the "Desktop development with C++" workload^)
    echo.
    echo The setup is resumable - run this again once that is sorted.
    echo.
    rmdir /s /q "%VENV%" 2>nul
    pause
    exit /b 1
)

echo.
echo Setup complete.
echo.

:run
"%VENV%\Scripts\python.exe" "%~dp0app.py" %*
if errorlevel 1 pause
