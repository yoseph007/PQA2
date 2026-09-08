import json
import logging
import os
import platform
import subprocess
import threading
import time
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

# Now using the improved utility functions
from .utils import get_ffmpeg_path, get_subprocess_startupinfo

logger = logging.getLogger(__name__)

# Constants for metric interpretation
PSNR_EXCELLENT = 40.0
PSNR_GOOD = 30.0
SSIM_EXCELLENT = 0.95
SSIM_GOOD = 0.90

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

VMAF_MODEL_FILES = {
    "vmaf_4k_v0.6.1": "vmaf_4k_v0.6.1.json",
    "vmaf_4k_v0.6.1neg": "vmaf_4k_v0.6.1neg.json",
    "vmaf_b_v0.6.3": "vmaf_b_v0.6.3.json",
    "vmaf_float_v0.6.1": "vmaf_float_v0.6.1.json",
    "vmaf_float_v0.6.1neg": "vmaf_float_v0.6.1neg.json",
    "vmaf_float_4k_v0.6.1": "vmaf_float_4k_v0.6.1.json",
    "vmaf_float_b_v0.6.3": "vmaf_float_b_v0.6.3.json",
}


class AnalysisCapabilityError(Exception):
    """Raised when required FFmpeg or libvmaf capabilities are missing or unsupported"""
    pass


PATH_ESCAPING_CANDIDATES = [
    ("triple_backslash", lambda p: f"path={p.replace(':', r'\\\:')}"),
    ("single_backslash", lambda p: f"path={p.replace(':', r'\:')}"),
    ("quoted_single_backslash", lambda p: f"path='{p.replace(':', r'\:')}'"),
    ("raw", lambda p: f"path={p}"),
]


def _normalize_path_for_filter(path: str) -> str:
    """Normalize path for FFmpeg filter on Windows (escapes colons for sub-options)"""
    p = os.path.abspath(path).replace('\\', '/')
    if platform.system() == 'Windows' and ':' in p:
        p = p.replace(':', r'\\\:')
    return p


def _normalize_log_path_for_filter(path: str) -> str:
    """Normalize log_path for FFmpeg filter on Windows with escaped colon in quotes"""
    p = os.path.abspath(path).replace('\\', '/')
    if platform.system() == 'Windows' and ':' in p:
        p = p.replace(':', r'\:')
    return f"'{p}'"


def format_model_path(path: str, escaping_form: str = None) -> str:
    """Format a model file path according to the probed/specified escaping form"""
    p = os.path.abspath(path).replace('\\', '/')
    if not escaping_form:
        if isinstance(VMAFAnalyzer._cached_capabilities, dict):
            for c_val in VMAFAnalyzer._cached_capabilities.values():
                if isinstance(c_val, dict) and "libvmaf_path_escaping" in c_val:
                    escaping_form = c_val["libvmaf_path_escaping"]
                    break
        elif VMAFAnalyzer._cached_capabilities is not None:
            try:
                escaping_form = VMAFAnalyzer._cached_capabilities.get("libvmaf_path_escaping")
            except Exception:
                pass
        if not escaping_form:
            escaping_form = "triple_backslash" if platform.system() == "Windows" else "raw"

    for name, fn in PATH_ESCAPING_CANDIDATES:
        if name == escaping_form:
            return fn(p)

    if platform.system() == "Windows":
        return f"path={p.replace(':', r'\\\:')}"
    return f"path={p}"


def build_vmaf_model_option(model: str, escaping_form: str = None) -> str:
    """Centralized VMAF model option string constructor"""
    if not model:
        model = "vmaf_v0.6.1"

    if os.path.isfile(model):
        return format_model_path(model, escaping_form=escaping_form)

    if model in VMAF_MODEL_FILES:
        target = os.path.join(MODELS_DIR, VMAF_MODEL_FILES[model])
        if os.path.isfile(target):
            return format_model_path(target, escaping_form=escaping_form)

    return f"version={model}"


class VMAFAnalyzer(QObject):
    """VMAF analyzer for measuring video quality with signals for UI integration"""
    analysis_progress = pyqtSignal(int)  # 0-100%
    analysis_complete = pyqtSignal(dict)  # VMAF results
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    _cached_capabilities = {}

    def __init__(self):
        super().__init__()
        self.output_directory = None
        self.test_name = None
        self._process_lock = threading.Lock()
        self._current_process = None
        self._terminate_requested = False
        self.threads = 4  # Default number of threads for VMAF analysis
        # Default values for advanced options
        self.pool_method = "mean"  # Options: mean, min, harmonic_mean
        self.enable_motion_score = False
        self.enable_temporal_features = False
        self.feature_subsample = 1
        self.psnr_enabled = True
        self.ssim_enabled = True
        self.delete_aligned_original = True

    @classmethod
    def _one_frame_dryrun(cls, ffmpeg_exe: str, model_opt: str):
        """Dry-run libvmaf with testsrc2 for 0.1s to verify model path formatting.
        Returns tuple (bool, stderr_str)."""
        try:
            startupinfo, creationflags = get_subprocess_startupinfo()
            filt = f"split[ref][dist];[dist][ref]libvmaf=model='{model_opt}':log_fmt=json"
            cmd = [
                ffmpeg_exe, "-y",
                "-f", "lavfi", "-i", "testsrc2=duration=0.1:size=64x64:rate=10",
                "-lavfi", filt,
                "-f", "null", "-"
            ]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=creationflags,
                timeout=5
            )
            return (res.returncode == 0, res.stderr or "")
        except Exception as e:
            logger.debug(f"Dryrun failed for model_opt='{model_opt}': {e}")
            return (False, str(e))

    @classmethod
    def _probe_model_path_form(cls, ffmpeg_exe: str, sample_model_path: str = None) -> str:
        """Determine which libvmaf path-escaping form this build accepts.
        Returns the winning template name, e.g. 'triple_backslash', 'single_backslash', etc."""
        if not sample_model_path:
            candidates_to_find = [
                os.path.join(MODELS_DIR, "vmaf_v0.6.1.json"),
                os.path.join(MODELS_DIR, "vmaf_4k_v0.6.1.json"),
            ]
            if os.path.isdir(MODELS_DIR):
                for f in os.listdir(MODELS_DIR):
                    if f.endswith(".json"):
                        candidates_to_find.insert(0, os.path.join(MODELS_DIR, f))
            for c in candidates_to_find:
                if os.path.isfile(c):
                    sample_model_path = os.path.abspath(c)
                    break

        if not sample_model_path or not os.path.isfile(sample_model_path):
            logger.warning("No sample model file available to probe path escaping; defaulting")
            return "triple_backslash" if platform.system() == "Windows" else "raw"

        norm_sample_path = sample_model_path.replace("\\", "/")
        err_msgs = []
        for form_name, form_fn in PATH_ESCAPING_CANDIDATES:
            model_opt = form_fn(norm_sample_path)
            res = cls._one_frame_dryrun(ffmpeg_exe, model_opt)
            if isinstance(res, tuple):
                ok, stderr_out = res
            else:
                ok, stderr_out = bool(res), ""
            if ok:
                logger.info(f"libvmaf path-escaping probe won by: {form_name}")
                return form_name
            if stderr_out:
                err_msgs.append(stderr_out)

        # Metrology diagnostic: Differentiate invalid model format from path syntax errors
        combined_err = " ".join(err_msgs).lower()
        if any(term in combined_err for term in ["could not read model", "invalid json", "failed to load model", "json parse error"]):
            raise AnalysisCapabilityError(
                f"Model file at '{sample_model_path}' failed to load due to malformed or corrupted model JSON, not path escaping."
            )

        raise AnalysisCapabilityError("No model path form accepted by libvmaf (filter syntax error)")

    @classmethod
    def probe_capabilities(cls, ffmpeg_exe=None):
        """Check FFmpeg libvmaf capabilities once per session per binary"""
        if not ffmpeg_exe:
            from .utils import get_ffmpeg_path
            ffmpeg_exe = str(get_ffmpeg_path())

        norm_exe = os.path.normcase(os.path.normpath(ffmpeg_exe))
        if isinstance(cls._cached_capabilities, dict) and norm_exe in cls._cached_capabilities:
            return cls._cached_capabilities[norm_exe]
        elif cls._cached_capabilities is not None and not isinstance(cls._cached_capabilities, dict):
            # Backward compatibility if tests set _cached_capabilities directly
            return cls._cached_capabilities

        caps = {
            "has_libvmaf": False,
            "has_psnr_feature": False,
            "has_float_ssim": False,
            "has_ssim_feature": False,
            "libvmaf_path_escaping": "unknown",
            "ffmpeg_version": "unknown",
        }
        try:
            startupinfo, creationflags = get_subprocess_startupinfo()

            v_res = subprocess.run(
                [ffmpeg_exe, "-version"],
                capture_output=True, text=True, timeout=10,
                startupinfo=startupinfo, creationflags=creationflags
            )
            if v_res.returncode == 0:
                first_line = v_res.stdout.splitlines()[0]
                caps["ffmpeg_version"] = first_line
                if "libvmaf" in v_res.stdout:
                    caps["has_libvmaf"] = True

            h_res = subprocess.run(
                [ffmpeg_exe, "-h", "filter=libvmaf"],
                capture_output=True, text=True, timeout=10,
                startupinfo=startupinfo, creationflags=creationflags
            )
            if h_res.returncode == 0 and "libvmaf" in h_res.stdout:
                caps["has_libvmaf"] = True
                caps["has_psnr_feature"] = True
                caps["has_float_ssim"] = True
                caps["has_ssim_feature"] = True

            if caps["has_libvmaf"]:
                caps["libvmaf_path_escaping"] = cls._probe_model_path_form(ffmpeg_exe)
            else:
                caps["libvmaf_path_escaping"] = "none"

        except AnalysisCapabilityError:
            raise
        except Exception as e:
            logger.warning(f"Error probing FFmpeg capabilities: {e}")

        if not isinstance(cls._cached_capabilities, dict):
            cls._cached_capabilities = {}
        cls._cached_capabilities[norm_exe] = caps
        return caps

    def _build_fallback_chain(self, metric: str = "psnr", stats_file: str = None, feature_subsample: int = None) -> str:
        """
        Build FFmpeg filterchain for standalone PSNR or SSIM analysis pass.
        Guarantees absolute stats_file paths and proper subsampling with select filter.
        Never uses invalid max_samples option.
        """
        if feature_subsample is None:
            feature_subsample = getattr(self, "feature_subsample", 1)

        if not stats_file:
            stats_file = f"{metric}.log"

        abs_stats = os.path.abspath(stats_file)
        stats_opt = _normalize_log_path_for_filter(abs_stats)

        if feature_subsample and feature_subsample > 1:
            return (
                f"[0:v]select='not(mod(n\\,{feature_subsample}))'[v0];"
                f"[1:v]select='not(mod(n\\,{feature_subsample}))'[v1];"
                f"[v0][v1]{metric}=stats_file={stats_opt}"
            )
        return f"{metric}=stats_file={stats_opt}"

    def set_options_from_manager(self, options_manager):
        """Set VMAF options from the options manager"""
        if not options_manager:
            logger.warning("No options manager provided, using default settings")
            return
            
        try:
            # Get VMAF settings
            vmaf_settings = options_manager.get_setting("vmaf") or {}
            
            # Set threads from settings (default to 4 if not found)
            self.threads = vmaf_settings.get("threads", 4)
            
            # Set feature subsample (default to 1 if not found)
            self.feature_subsample = vmaf_settings.get("feature_subsample", 1)
            
            # Set other options
            self.pool_method = vmaf_settings.get("pool_method", "mean")
            self.enable_motion_score = vmaf_settings.get("enable_motion_score", False)
            self.enable_temporal_features = vmaf_settings.get("enable_temporal_features", False)
            self.psnr_enabled = vmaf_settings.get("psnr_enabled", True)
            self.ssim_enabled = vmaf_settings.get("ssim_enabled", True)
            self.delete_aligned_original = vmaf_settings.get("delete_aligned_original", True)
            
            logger.info(f"VMAF options set from manager: threads={self.threads}, "
                    f"feature_subsample={self.feature_subsample}, pool={self.pool_method}")
        except Exception as e:
            logger.error(f"Error setting VMAF options from manager: {e}")



    def set_output_directory(self, output_dir):
        """Set output directory for results"""
        self.output_directory = output_dir
        logger.info(f"Set output directory to: {self.output_directory}")

    def set_test_name(self, test_name):
        """Set test name for organizing results"""
        self.test_name = test_name
        logger.info(f"Set test name to: {test_name}")
        
    def set_advanced_options(self, pool_method="mean", enable_motion_score=False, 
                            enable_temporal_features=False, feature_subsample=1,
                            psnr_enabled=True, ssim_enabled=True):
        """Set advanced VMAF analysis options for fine-tuning"""
        self.pool_method = pool_method
        self.enable_motion_score = enable_motion_score
        self.enable_temporal_features = enable_temporal_features
        self.feature_subsample = feature_subsample
        self.psnr_enabled = psnr_enabled
        self.ssim_enabled = ssim_enabled
        
        logger.info(f"Set advanced VMAF options: pool={pool_method}, "
                    f"motion_score={enable_motion_score}, "
                    f"temporal={enable_temporal_features}, "
                    f"feature_subsample={feature_subsample}, "
                    f"psnr_enabled={psnr_enabled}, "
                    f"ssim_enabled={ssim_enabled}")

    def terminate_analysis(self):
        """Terminate running analysis"""
        self._terminate_requested = True
        if self._current_process:
            try:
                logger.info("Terminating VMAF analysis process")
                self._current_process.terminate()
                time.sleep(0.5)
                if self._current_process.poll() is None:
                    logger.info("Force killing VMAF analysis process")
                    self._current_process.kill()
            except Exception as e:
                logger.error(f"Error terminating VMAF process: {e}")

    def _prepare_ffmpeg_path(self, path):
        """Format an absolute path for FFmpeg use in Windows with forward slashes"""
        if not path:
            return ""
        return os.path.abspath(path).replace('\\', '/')

    def get_video_metadata(self, video_path, ffprobe_exe=None):
        """Extract comprehensive video metadata using FFprobe with JSON output"""
        try:
            if not video_path or not os.path.exists(video_path):
                logger.error(f"Video file not found: {video_path}")
                return None

            # Get FFprobe executable
            if not ffprobe_exe:
                from .utils import get_ffmpeg_path
                _, ffprobe_exe, _ = get_ffmpeg_path()

            
            # Normalize path for FFprobe
            video_path_norm = self._prepare_ffmpeg_path(video_path)
            
            # Get detailed video information
            cmd = [
                ffprobe_exe,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path_norm
            ]
            
            startupinfo, creationflags = get_subprocess_startupinfo()
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                startupinfo=startupinfo,
                creationflags=creationflags,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"FFprobe failed: {result.stderr}")
                return None
                
            info = json.loads(result.stdout)
            
            # Find video stream
            video_stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
            if not video_stream:
                logger.error(f"No video stream found in {video_path}")
                return None
                
            # Parse frame rate using Fraction
            fr_str = video_stream.get('avg_frame_rate', '0/1')
            try:
                frame_rate = float(Fraction(fr_str)) if '/' in fr_str else float(fr_str)
            except Exception:
                frame_rate = 0.0

            format_info = info.get('format', {})
            duration = float(format_info.get('duration', 0))

            nb_frames = video_stream.get('nb_frames')
            try:
                nb_frames = int(nb_frames) if nb_frames is not None else None
            except (ValueError, TypeError):
                nb_frames = None

            if not nb_frames and frame_rate > 0 and duration > 0:
                nb_frames = int(round(frame_rate * duration))
            elif not nb_frames:
                nb_frames = 0
                
            # Get metadata
            metadata = {
                'path': video_path,
                'duration': duration,
                'frame_rate': frame_rate,
                'fps': frame_rate,
                'width': int(video_stream.get('width', 0)),
                'height': int(video_stream.get('height', 0)),
                'pix_fmt': video_stream.get('pix_fmt', 'unknown'),
                'codec_name': video_stream.get('codec_name', 'unknown'),
                'bit_rate': int(format_info.get('bit_rate', 0)),
                'nb_frames': nb_frames,
                'total_frames': nb_frames,
                'frame_count': nb_frames,
            }
            
            logger.info(f"Video metadata extracted: {metadata['width']}x{metadata['height']} @ {metadata['frame_rate']}fps, {nb_frames} frames")
            return metadata
            
        except Exception as e:
            logger.error(f"Error extracting video metadata: {str(e)}")
            return None

    def analyze_videos(
        self,
        reference_path,
        distorted_path,
        model="vmaf_v0.6.1",
        duration=None,
        alignment_metadata=None,
        capture_metadata=None,
    ):
        """Run VMAF analysis with the correct command format and properly escaped paths"""
        
        import psutil
        cpu_count = psutil.cpu_count(logical=True)
        logger.debug(f"System has {cpu_count} logical CPUs")
        logger.debug(f"Current CPU usage: {psutil.cpu_percent(interval=0.1)}%")
        
        logger.info("VMAF analyzer starting")
        with self._process_lock:  # Use lock to prevent duplicate processing
            try:
                self._terminate_requested = False
                self.status_update.emit(f"Analyzing videos with model: {model}")
                logger.info(f"Starting VMAF analysis with model: {model}")

                # Verify files
                if not os.path.exists(reference_path):
                    error_msg = f"Reference video not found: {reference_path}"
                    logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    return None

                if not os.path.exists(distorted_path):
                    error_msg = f"Distorted video not found: {distorted_path}"
                    logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    return None

                logger.info(f"VMAF Reference: {reference_path}")
                logger.info(f"VMAF Distorted: {distorted_path}")

                ffmpeg_exe, ffprobe_exe, ffplay_exe = get_ffmpeg_path()

                # Get video metadata for validation and progress estimation
                ref_meta = self.get_video_metadata(reference_path, ffprobe_exe)
                dist_meta = self.get_video_metadata(distorted_path, ffprobe_exe)

                # Validate identical resolutions between reference and distorted
                if ref_meta and dist_meta:
                    rw, rh = ref_meta.get('width', 0), ref_meta.get('height', 0)
                    dw, dh = dist_meta.get('width', 0), dist_meta.get('height', 0)
                    if rw > 0 and dw > 0 and (rw != dw or rh != dh):
                        error_msg = (
                            f"Resolution mismatch between reference ({rw}x{rh}) "
                            f"and distorted ({dw}x{dh}). VMAF requires identical resolutions."
                        )
                        logger.error(error_msg)
                        self.error_occurred.emit(error_msg)
                        return None

                output_dir = self.output_directory
                if not output_dir:
                    output_dir = os.path.dirname(reference_path)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                test_name = self.test_name or "Test"

                parent_dir = os.path.dirname(reference_path)
                if test_name and test_name in parent_dir:
                    test_dir = parent_dir
                    logger.info(f"Using existing test directory: {test_dir}")
                else:
                    test_dir = os.path.join(output_dir, f"{test_name}_{timestamp}")
                    os.makedirs(test_dir, exist_ok=True)
                    logger.info(f"Created test results directory: {test_dir}")

                vmaf_filename = f"{test_name}_{timestamp}_vmaf.json"
                psnr_filename = f"{test_name}_{timestamp}_psnr.txt"
                ssim_filename = f"{test_name}_{timestamp}_ssim.txt"

                json_path = os.path.join(test_dir, vmaf_filename)
                psnr_path = os.path.join(test_dir, psnr_filename)
                ssim_path = os.path.join(test_dir, ssim_filename)

                total_frames = 0
                if dist_meta:
                    if dist_meta.get('nb_frames', 0) > 0:
                        total_frames = dist_meta.get('nb_frames')
                    elif dist_meta.get('frame_rate', 0) > 0 and dist_meta.get('duration', 0) > 0:
                        total_frames = int(dist_meta.get('frame_rate') * dist_meta.get('duration'))

                logger.info(f"Estimated total frames: {total_frames}")

                if model is None:
                    model = "vmaf_v0.6.1"
                    logger.info(f"No model specified, using default model: {model}")

                caps = self.probe_capabilities(ffmpeg_exe)
                logger.info(f"FFmpeg probe capabilities: {caps}")

                # Build VMAF options
                log_path_opt = _normalize_log_path_for_filter(json_path)
                model_opt = build_vmaf_model_option(model, escaping_form=caps.get("libvmaf_path_escaping"))

                vmaf_options = [
                    f"log_path={log_path_opt}",
                    "log_fmt=json",
                    f"model='{model_opt}'",
                    f"n_threads={self.threads if hasattr(self, 'threads') else 4}",
                ]

                if self.feature_subsample > 1:
                    vmaf_options.append(f"n_subsample={self.feature_subsample}")

                if self.pool_method != "mean":
                    vmaf_options.append(f"pool={self.pool_method}")

                # Features: single-pass inside libvmaf when supported
                features = []
                single_pass_psnr_ssim = False
                if caps.get("has_libvmaf"):
                    if caps.get("has_psnr_feature") and self.psnr_enabled:
                        features.append("name=psnr")
                    if caps.get("has_float_ssim") and self.ssim_enabled:
                        features.append("name=float_ssim")
                    elif caps.get("has_ssim_feature") and self.ssim_enabled:
                        features.append("name=ssim")

                    if "neg" in str(model).lower():
                        features.append("name=neg")

                    if self.enable_motion_score:
                        features.append("name=motion")

                    if self.enable_temporal_features:
                        features.extend([
                            "name=vif_scale0",
                            "name=vif_scale1",
                            "name=vif_scale2",
                            "name=vif_scale3",
                            "name=adm2"
                        ])
                        if "name=motion" not in features:
                            features.append("name=motion")

                    if features:
                        vmaf_options.append(f"feature='{'|'.join(features)}'")

                    if (not self.psnr_enabled or caps.get("has_psnr_feature")) and (
                        not self.ssim_enabled or caps.get("has_float_ssim") or caps.get("has_ssim_feature")
                    ):
                        single_pass_psnr_ssim = True

                vmaf_filter = f"libvmaf={':'.join(vmaf_options)}"
                logger.info(f"VMAF filter: {vmaf_filter}")

                dist_input = self._prepare_ffmpeg_path(distorted_path)
                ref_input = self._prepare_ffmpeg_path(reference_path)

                cmd = [
                    ffmpeg_exe,
                    "-hide_banner",
                    "-loglevel", "info",
                    "-i", dist_input,
                    "-i", ref_input,
                    "-lavfi", vmaf_filter,
                    "-f", "null", "-"
                ]

                logger.info(f"VMAF Command: {' '.join(cmd)}")

                startupinfo, creationflags = get_subprocess_startupinfo()
                env = os.environ.copy()
                env.update({
                    "FFMPEG_HIDE_BANNER": "1",
                    "AV_LOG_FORCE_NOCOLOR": "1"
                })

                self.analysis_progress.emit(0)
                self.status_update.emit("Starting VMAF analysis...")

                try:
                    self._current_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        startupinfo=startupinfo,
                        creationflags=creationflags,
                        env=env
                    )

                    stderr_lines = []
                    last_progress_time = time.time()
                    frame_count = 0

                    for line in iter(self._current_process.stderr.readline, ''):
                        if self._terminate_requested:
                            logger.info("VMAF analysis termination requested")
                            break

                        stderr_lines.append(line)

                        if "frame=" in line or "speed=" in line or "VMAF score" in line:
                            logger.info(f"VMAF progress: {line.strip()}")

                        if "frame=" in line:
                            try:
                                frame_info = line.split("frame=")[1].split()[0].strip()
                                if frame_info.isdigit():
                                    frame_count = int(frame_info)
                                    if total_frames > 0:
                                        progress = min(95, int((frame_count / total_frames) * 100))
                                        current_time = time.time()
                                        if current_time - last_progress_time > 0.5:
                                            self.analysis_progress.emit(progress)
                                            last_progress_time = current_time
                                            self.status_update.emit(f"Processing frame {frame_count}/{total_frames} ({progress}%)")
                            except Exception as e:
                                logger.debug(f"Error parsing frame progress: {str(e)}")

                        if self._current_process.poll() is not None:
                            logger.info("VMAF process completed")
                            break

                    remaining_stderr = self._current_process.stderr.read()
                    if remaining_stderr:
                        stderr_lines.append(remaining_stderr)

                    returncode = self._current_process.wait(timeout=10)
                    error = ''.join(stderr_lines)

                    logger.info(f"VMAF process completed with return code: {returncode}")
                    self._current_process = None

                    if self._terminate_requested:
                        error_msg = "VMAF analysis was terminated by user"
                        logger.warning(error_msg)
                        self.error_occurred.emit(error_msg)
                        return None

                    if returncode != 0:
                        error_msg = f"VMAF analysis failed with return code {returncode}: {error}"
                        logger.error(error_msg)
                        self.error_occurred.emit(error_msg)
                        return None

                except subprocess.TimeoutExpired:
                    error_msg = "VMAF analysis timed out"
                    logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    if self._current_process:
                        try:
                            self._current_process.kill()
                            self._current_process.wait(timeout=5)
                        except Exception:
                            pass
                        self._current_process = None
                    return None

                except Exception as e:
                    error_msg = f"Error running VMAF analysis: {str(e)}"
                    logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    if self._current_process:
                        try:
                            self._current_process.kill()
                            self._current_process.wait(timeout=5)
                        except Exception:
                            pass
                        self._current_process = None
                    return None

                finally:
                    if self._current_process:
                        try:
                            if self._current_process.poll() is None:
                                self._current_process.terminate()
                                time.sleep(0.5)
                                if self._current_process.poll() is None:
                                    self._current_process.kill()
                        except Exception:
                            pass
                        self._current_process = None

                # Fallback separate-pass if single pass features were not available
                if not single_pass_psnr_ssim and (self.psnr_enabled or self.ssim_enabled):
                    self.status_update.emit("VMAF completed, running fallback PSNR/SSIM analysis...")
                    psnr_target = psnr_path if self.psnr_enabled else None
                    ssim_target = ssim_path if self.ssim_enabled else None
                    psnr_ssim_success = self._run_psnr_ssim_analysis(
                        ffmpeg_exe,
                        dist_input,
                        ref_input,
                        psnr_target,
                        ssim_target,
                    )
                    if not psnr_ssim_success:
                        logger.warning("Fallback PSNR/SSIM analysis failed, but continuing with VMAF results")
                elif single_pass_psnr_ssim:
                    logger.info("PSNR and SSIM computed in single-pass within libvmaf")
                else:
                    logger.info("Skipping PSNR/SSIM analysis as they are disabled")

                return self._parse_vmaf_results(
                    json_path=json_path,
                    psnr_path=psnr_path if self.psnr_enabled else None,
                    ssim_path=ssim_path if self.ssim_enabled else None,
                    distorted_path=distorted_path,
                    reference_path=reference_path,
                    model=model,
                    alignment_metadata=alignment_metadata,
                    capture_metadata=capture_metadata,
                    caps=caps,
                )

            except Exception as e:
                error_msg = f"Error in VMAF analysis: {str(e)}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                import traceback
                logger.error(traceback.format_exc())
                return None













    def _parse_vmaf_results(
        self,
        json_path,
        psnr_path=None,
        ssim_path=None,
        distorted_path="",
        reference_path="",
        model="vmaf_v0.6.1",
        alignment_metadata=None,
        capture_metadata=None,
        caps=None,
    ):
        """Parse VMAF results from the output files"""
        try:
            # Check if output files exist
            if not os.path.exists(json_path):
                error_msg = "VMAF analysis completed but JSON output file not found"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return None

            # Parse VMAF results from JSON
            try:
                with open(json_path, 'r') as f:
                    vmaf_data = json.load(f)

                # Extract scores
                vmaf_score = None
                psnr_score = None
                ssim_score = None

                if "pooled_metrics" in vmaf_data:
                    try:
                        pool = vmaf_data["pooled_metrics"]
                        if "vmaf" in pool:
                            vmaf_score = float(pool["vmaf"]["mean"])
                        if "float_ssim" in pool:
                            ssim_score = float(pool["float_ssim"]["mean"])
                        elif "ssim" in pool:
                            ssim_score = float(pool["ssim"]["mean"])
                        elif "ssim_y" in pool:
                            ssim_score = float(pool["ssim_y"]["mean"])

                        if "psnr_y" in pool:
                            psnr_score = float(pool["psnr_y"]["mean"])
                        elif "psnr" in pool:
                            psnr_score = float(pool["psnr"]["mean"])
                    except Exception as e:
                        logger.error(f"Error parsing VMAF metrics from pooled_metrics: {e}")

                elif "frames" in vmaf_data:
                    frames = vmaf_data["frames"]
                    if frames:
                        vmaf_values = []
                        psnr_values = []
                        ssim_values = []

                        for frame in frames:
                            metrics = frame.get("metrics", {})
                            if "vmaf" in metrics:
                                vmaf_values.append(metrics["vmaf"])
                            if "float_ssim" in metrics:
                                ssim_values.append(metrics["float_ssim"])
                            elif "ssim" in metrics:
                                ssim_values.append(metrics["ssim"])
                            elif "ssim_y" in metrics:
                                ssim_values.append(metrics["ssim_y"])
                            if "psnr_y" in metrics:
                                psnr_values.append(metrics["psnr_y"])
                            elif "psnr" in metrics:
                                psnr_values.append(metrics["psnr"])

                        if vmaf_values:
                            vmaf_score = sum(vmaf_values) / len(vmaf_values)
                        if psnr_values:
                            psnr_score = sum(psnr_values) / len(psnr_values)
                        if ssim_values:
                            ssim_score = sum(ssim_values) / len(ssim_values)

                # Fallback to separate files if not found in libvmaf output
                if (psnr_score is None or psnr_score == 0) and psnr_path and os.path.exists(psnr_path):
                    try:
                        with open(psnr_path, 'r') as f:
                            for line in f:
                                if "average" in line.lower() and "psnr" in line.lower():
                                    import re
                                    match = re.search(r'(\d+\.\d+)', line)
                                    if match:
                                        psnr_score = float(match.group(1))
                                        break
                    except Exception as e:
                        logger.warning(f"Error parsing PSNR from file: {e}")

                if (ssim_score is None or ssim_score == 0) and ssim_path and os.path.exists(ssim_path):
                    try:
                        with open(ssim_path, 'r') as f:
                            for line in f:
                                if "average" in line.lower() and "ssim" in line.lower():
                                    import re
                                    match = re.search(r'(\d+\.\d+)', line)
                                    if match:
                                        ssim_score = float(match.group(1))
                                        break
                    except Exception as e:
                        logger.warning(f"Error parsing SSIM from file: {e}")

                logger.info(f"VMAF Score: {vmaf_score}")
                logger.info(f"PSNR Score: {psnr_score}")
                logger.info(f"SSIM Score: {ssim_score}")

                raw_results = vmaf_data
                _, ffprobe_exe, _ = get_ffmpeg_path()
                dist_meta = self.get_video_metadata(distorted_path, ffprobe_exe)
                self.get_video_metadata(reference_path, ffprobe_exe)

                # Dimensions and duration
                width = dist_meta.get('width', 0) if dist_meta else 0
                height = dist_meta.get('height', 0) if dist_meta else 0
                frame_count = dist_meta.get('nb_frames', 0) if dist_meta else 0
                duration = dist_meta.get('duration', 0) if dist_meta else 0
                fps = dist_meta.get('frame_rate', 0) if dist_meta else 0

                if frame_count == 0 and fps > 0 and duration > 0:
                    frame_count = int(round(fps * duration))

                reference_filename = os.path.basename(reference_path) if reference_path else ""
                distorted_filename = os.path.basename(distorted_path) if distorted_path else ""

                model_info = model
                if isinstance(vmaf_data, dict):
                    if "model" in vmaf_data:
                        model_info = vmaf_data["model"]
                    elif "version" in vmaf_data:
                        model_info = vmaf_data["version"]

                results = {
                    'vmaf_score': vmaf_score,
                    'vmaf': vmaf_score,
                    'psnr_score': psnr_score,
                    'psnr': psnr_score,
                    'ssim_score': ssim_score,
                    'ssim': ssim_score,
                    'json_path': json_path,
                    'psnr_log': psnr_path,
                    'ssim_log': ssim_path,
                    'reference_video': reference_filename,
                    'distorted_video': distorted_filename,
                    'reference_path': reference_path,
                    'distorted_path': distorted_path,
                    'aligned_path': distorted_path,
                    'raw_results': raw_results,
                    'metadata': {
                        'test': {
                            'model': model_info,
                            'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'test_name': self.test_name or "Unnamed Test"
                        },
                        'video': {
                            'width': width,
                            'height': height,
                            'frame_count': frame_count,
                            'duration': duration,
                            'fps': fps,
                            'format': dist_meta.get('pix_fmt', 'unknown') if dist_meta else 'unknown',
                            'codec': dist_meta.get('codec_name', 'unknown') if dist_meta else 'unknown',
                            'bitrate': dist_meta.get('bit_rate', 0) if dist_meta else 0
                        },
                        'vmaf_options': {
                            'pool_method': self.pool_method,
                            'feature_subsample': self.feature_subsample,
                            'motion_score': self.enable_motion_score,
                            'temporal_features': self.enable_temporal_features
                        }
                    },
                    'measurement_metadata': {
                        'alignment': alignment_metadata or {},
                        'capture': capture_metadata or {},
                        'model': model,
                        'libvmaf_version': (caps or {}).get('ffmpeg_version', 'unknown'),
                        'libvmaf_path_escaping': (caps or {}).get('libvmaf_path_escaping', 'unknown'),
                    }
                }

                self.analysis_progress.emit(100)
                score_str = f"{vmaf_score:.2f}" if isinstance(vmaf_score, (int, float)) else str(vmaf_score)
                self.status_update.emit(f"VMAF analysis complete! Score: {score_str}")

                # Handle file cleanup
                if self.delete_aligned_original:
                    aligned_capture = results.get('aligned_path') or results.get('distorted_path')
                    if aligned_capture and "aligned" in os.path.basename(aligned_capture).lower():
                        candidate_original = aligned_capture.replace("_aligned", "")
                        if candidate_original != aligned_capture and os.path.isfile(candidate_original):
                            try:
                                logger.info(f"Deleting original unaligned capture file: {candidate_original}")
                                os.remove(candidate_original)
                            except Exception as cleanup_error:
                                logger.warning(f"Could not delete original capture file {candidate_original}: {cleanup_error}")

                self.analysis_complete.emit(results)
                return results

            except Exception as e:
                error_msg = f"Error parsing VMAF results: {str(e)}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                import traceback
                logger.error(traceback.format_exc())
                return None

        except Exception as e:
            error_msg = f"Error processing VMAF results: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _run_psnr_ssim_analysis(self, ffmpeg_exe, distorted_path, reference_path, psnr_path, ssim_path):
        """Run PSNR and SSIM analysis separately using absolute paths (fallback branch)"""
        try:
            startupinfo, creationflags = get_subprocess_startupinfo()
            env = os.environ.copy()
            env.update({
                "FFMPEG_HIDE_BANNER": "1",
                "AV_LOG_FORCE_NOCOLOR": "1",
                "SDL_VIDEODRIVER": "dummy",
                "SDL_AUDIODRIVER": "dummy"
            })

            results_ok = [False, False]

            dist_input = self._prepare_ffmpeg_path(distorted_path)
            ref_input = self._prepare_ffmpeg_path(reference_path)

            if psnr_path:
                logger.info("Running fallback PSNR analysis...")
                self.status_update.emit("Running fallback PSNR analysis...")
                psnr_filter = self._build_fallback_chain(
                    metric="psnr",
                    stats_file=psnr_path,
                    feature_subsample=self.feature_subsample
                )
                psnr_cmd = [
                    ffmpeg_exe,
                    "-hide_banner",
                    "-i", dist_input,
                    "-i", ref_input,
                    "-lavfi", psnr_filter,
                    "-f", "null", "-"
                ]
                psnr_result = subprocess.run(
                    psnr_cmd,
                    check=False,
                    capture_output=True,
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                    env=env,
                    timeout=120
                )
                if psnr_result.returncode != 0:
                    logger.warning(f"PSNR analysis failed: {psnr_result.stderr}")
                else:
                    logger.info("PSNR analysis completed successfully")
                    results_ok[0] = True

            if ssim_path:
                logger.info("Running fallback SSIM analysis...")
                self.status_update.emit("Running fallback SSIM analysis...")
                ssim_filter = self._build_fallback_chain(
                    metric="ssim",
                    stats_file=ssim_path,
                    feature_subsample=self.feature_subsample
                )
                ssim_cmd = [
                    ffmpeg_exe,
                    "-hide_banner",
                    "-i", dist_input,
                    "-i", ref_input,
                    "-lavfi", ssim_filter,
                    "-f", "null", "-"
                ]
                ssim_result = subprocess.run(
                    ssim_cmd,
                    check=False,
                    capture_output=True,
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                    env=env,
                    timeout=120
                )
                if ssim_result.returncode != 0:
                    logger.warning(f"SSIM analysis failed: {ssim_result.stderr}")
                else:
                    logger.info("SSIM analysis completed successfully")
                    results_ok[1] = True

            return (results_ok[0] or not psnr_path) and (results_ok[1] or not ssim_path)
        except subprocess.TimeoutExpired:
            logger.warning("PSNR/SSIM analysis timed out")
            return False
        except Exception as e:
            logger.warning(f"Error running PSNR/SSIM analysis: {e}")
            return False































