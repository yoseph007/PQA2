:: clean-imports.bat
@echo off
autoflake --in-place --remove-unused-variables --remove-all-unused-imports -r app
