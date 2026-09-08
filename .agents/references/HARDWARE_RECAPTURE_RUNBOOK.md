# Hardware Re-Capture Campaign Protocol (Gage R&R)

This runbook defines the authoritative operational protocol for the Capstone Metrology Campaign: measuring physical capture-chain jitter ($\sigma_{\text{rig}}$ and $\%CV_{\text{rig}}$) on real hardware.

---

## Founding Metrological Question
> *When two displays or test runs differ by $X$ VMAF points, how much of $X$ is the display under test and how much is the measurement ruler?*

Until this protocol is executed, all statistical uncertainty gates rely on a declared resolution floor ($\sigma_{\text{floor}} = 0.05$). The execution of this protocol replaces that declared convention with an **empirical, hardware-derived repeatability uncertainty** ($\sigma_{\text{rig}}$).

---

## 5-Step Session Execution Protocol

### Step 1: Cold-Machine Bootstrap & Preflight Device Enumeration
Validate cold-machine setup, ensure virtual environment sync, verify pre-commit hooks, and enumerate real hardware capture cards.

1. **Run Dev Bootstrap**:
   ```cmd
   setup_dev.bat
   ```
2. **Execute System Preflight**:
   ```cmd
   .\.venv\Scripts\python.exe scripts\preflight_check.py
   ```
3. **Acceptance Criteria**:
   - Python $\ge 3.10$ and all 8 core packages imported `[PASS]`.
   - FFmpeg executable with `libvmaf` filter present `[PASS]`.
   - Storage preflight passes for capture directory disk space `[PASS]`.
   - Hardware capture device enumerated (e.g., Blackmagic Intensity Shuttle, DeckLink) `[PASS]`.

---

### Step 2: Live-Fire Watchdog Validation (Negative Fault Injection)
Validate that hardware disconnection mid-capture triggers the stall detector, shuts down FFmpeg cleanly without zombie processes, displays the amber UI warning banner, and logs a failed pass without aborting future campaign runs.

1. **Launch App or Capture Pipeline**:
   ```cmd
   run_app.bat
   ```
   Navigate to **Capture Tab**, select the active DeckLink/HDMI input device, and set capture duration to 30 seconds.
2. **Inject Fault**:
   - Click **Start Capture**.
   - After ~5 seconds of active capture, **physically disconnect the HDMI cable** or power off the source feed.
3. **Observe & Verify**:
   - **Stall Detection**: After $\approx 5.0\text{s}$ of ingestion silence, the watchdog triggers:
     `WATCHDOG TRIGGERED: Video ingestion stalled: no frames received for 5.0s`.
   - **Amber UI Telemetry**: The UI transitions safely, displaying the amber warning banner:
     `"Capture stalled: no frames received from device..."`.
   - **Zero Zombie FFmpeg Verification**: After the banner clears, verify via Task Manager or PowerShell that zero `ffmpeg.exe` processes remain:
     ```cmd
     powershell -Command "Get-Process ffmpeg -ErrorAction SilentlyContinue"
     ```
   - **Precedence Guarantee**: Signal `capture_failed` takes precedence over any `capture_completed` signal.
   - **Repeatability Ledger**: If running a multi-pass campaign, the pass is recorded as failed, and the campaign continues to subsequent passes.
   - **Archival**: Archive console log output and UI screenshot showing the amber banner as evidence.

---

### Step 3: Multi-Capture Re-Capture Campaign ($N = 8\text{--}10$)
Capture $N \ge 5$ (recommended: $N = 8\text{--}10$) independent physical video passes of the identical display loop under identical capture card settings, without changing video format, resolution, or cable routing.

1. **Reference Video Fixture**:
   - Select the golden reference video (e.g., `tests/test_references/DANCE_.mp4` or target master loop).
2. **Capture Execution & Bookend Alignment Gate**:
   - Execute captures through the GUI Capture Tab (or automated script) into `captures/`:
     - `captures/recapture_pass_01_aligned.mp4`
     - `captures/recapture_pass_02_aligned.mp4`
     - ...
     - `captures/recapture_pass_10_aligned.mp4`
   - **Alignment Gate**: Ensure every capture pass is frame-aligned via bookend markers. Capture-to-capture frame counts must be identical; content misalignment invalidates Gage R&R.

---

### Step 4: Multi-Capture Gage R&R Analysis & Configuration Logging
Execute the dedicated hardware re-capture campaign analyzer to compute the rig's empirical statistics, log the campaign to `logs/campaign_history.jsonl` with `campaign_type: "recapture"`, record full run parameters, and export the metrology certificate.

1. **Execute Campaign Runner**:
   ```cmd
   .\.venv\Scripts\python.exe scripts\run_recapture_campaign.py ^
       --ref tests/test_references/DANCE_.mp4 ^
       --captures "captures/recapture_pass_*_aligned.mp4" ^
       --device "Blackmagic Intensity Shuttle" ^
       --display-setting "1080p29.97 SDR HDMI Native" ^
       --out-pdf reports/gage_rr_hardware_recapture.pdf ^
       --test-name "HDMI Ingestion Chain Hardware Repeatability (10 Passes)"
   ```
2. **Review Campaign Terminal Output & Frame Alignment Gate**:
   - The runner asserts that all capture passes share identical frame counts and match the reference span.
   - Computes sample mean $\bar{V}$, sample standard deviation $\sigma_{\text{rig}}$ (with Bessel's correction $N-1$), range, and $\%CV_{\text{rig}} = \frac{\sigma_{\text{rig}}}{\bar{V}} \times 100\%$.
   - **Honest Framing**: Expect non-zero $\sigma_{\text{rig}}$ (typically 0.05–0.50 VMAF points). Any measured figure is a valid empirical characterization of the rig.
   - Confirm Gage R&R verdict:
     - **Acceptable**: $\%CV < 1.0\%$ (ideal hardware repeatability).
     - **Marginal**: $1.0\% \le \%CV < 5.0\%$.
     - **Unacceptable**: $\%CV \ge 5.0\%$.

---

### Step 5: Capture-to-Capture Noise Floor Verification & Final PDF Certificate

1. **Run Pairwise Campaign Comparison with Measured $\sigma_{\text{rig}}$**:
   Evaluate whether capture-to-capture noise between two individual passes ever clears the *measured* instrument resolution:
   ```cmd
   .\.venv\Scripts\python.exe scripts\compare_campaigns.py --latest 2 --sigma-floor <measured_sigma_rig>
   ```
   *(Note: The diff engine automatically detects `campaign_type == "recapture"` and applies $\sigma_{\text{floor\_effective}} = \max(0.05, \sigma_{\text{rig}})$).*
2. **Significance & Noise Floor Check**:
   - Confirm $\Delta\text{VMAF}$ between physical passes of identical content does *not* clear the empirical $3\sigma_{\Delta}$ noise floor:
     `Verdict: Indistinguishable from Instrument Noise (within 3*sigma_delta)`
   - SNR should be $< 1.0\times$, proving the instrument does not report false deltas on identical inputs.
3. **Inspect Final PDF Report**:
   Open `reports/gage_rr_hardware_recapture.pdf`:
   - **Hardware Characterization Banner**:
     `"Hardware Characterization: Re-capture campaign across independent physical display passes. %CV represents empirical capture-chain uncertainty (Gage R&R repeatability)."`
   - **Run Parameters Recorded**: Hardware device name, display settings, resolution/fps, and golden reference SHA-256 are printed in the Measurement Conditions table.
   - **Metrological Validation Matrix**:
     All 4 rows are certified:
     - Metrics Non-Degenerate: `[PASS VERIFIED]`
     - Near-Lossless Advisory: `[PASS VERIFIED]`
     - Pipeline Determinism: `[PASS PROVED]`
     - Rig Repeatability / Uncertainty: `[PASS CERTIFIED]` (empirically populated with $\sigma_{\text{rig}}$ and $\%CV_{\text{rig}}$).
   - The metrology claims matrix is now 100% closed with zero unmeasured claims remaining.
