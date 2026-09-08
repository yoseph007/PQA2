@echo off
echo Setting up Git hooks...

if not exist ".git\hooks" (
    echo Error: .git\hooks directory not found. Are you in the root of the repository?
    exit /b 1
)

copy scripts\pre-commit .git\hooks\pre-commit
if errorlevel 1 (
    echo Failed to copy pre-commit hook.
    exit /b 1
)

echo Hook installed successfully.
exit /b 0
