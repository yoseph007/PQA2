---
name: run-vmaf-tests
description: Executes the test suite for the VMAF application and handles Qt-specific testing setups.
---

# Run VMAF Tests Skill

## Context
This project uses `pytest` and `pytest-qt` for testing the PyQt5 application and its various backend managers (capture, vmaf, alignment).

## Instructions
When instructed to run tests, follow these steps:
1. Ensure you are in the workspace root directory: `c:\Apps\VMAF_2app_approach\VMAF\VB01-vmaf-app`.
2. Run the test suite using the provided `run_tests.py` script, which handles environment setup and invokes pytest correctly.
3. If running via terminal command:
   ```bash
   python run_tests.py
   ```
4. If a specific test file needs to be run, you can run pytest directly on that file:
   ```bash
   pytest tests/test_specific_file.py -v
   ```
5. **Handling Test Failures**: If tests related to UI components fail, verify that `pytest-qt` fixtures (`qtbot`) are correctly injecting mocked components or handling threading properly. 
