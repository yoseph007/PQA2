import os
import subprocess

__version__ = "1.0.1-alpha.1"


def get_git_commit(short=True) -> str:
    """Retrieve the current git commit hash, with graceful fallback."""
    try:
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = ["git", "rev-parse", "--short", "HEAD"] if short else ["git", "rev-parse", "HEAD"]
        result = subprocess.run(
            cmd,
            cwd=repo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
            check=False
        )
        if result.returncode == 0:
            commit = result.stdout.strip()
            if commit:
                return commit
    except Exception:
        pass

    # Fallback to environment variable if set (CI/CD environments)
    env_commit = os.environ.get("GIT_COMMIT", os.environ.get("GITHUB_SHA", "unknown"))
    if env_commit and env_commit != "unknown":
        return env_commit[:7] if short else env_commit
    return "unknown"


def get_version_string() -> str:
    """Return unified formatted version string, e.g. 'v1.0.1-alpha.1 (a1b2c3d)'."""
    commit = get_git_commit(short=True)
    if commit and commit != "unknown":
        return f"v{__version__} ({commit})"
    return f"v{__version__}"
