#!/usr/bin/env python3
"""
Universal runner for NotebookLM skill scripts
Ensures all scripts run with the correct virtual environment
"""

import os
import sys
import subprocess
import shutil
import platform
from pathlib import Path


def get_venv_python():
    """Get the virtual environment Python executable"""
    skill_dir = Path(__file__).parent.parent
    venv_dir = skill_dir / ".venv"

    if os.name == 'nt':  # Windows
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:  # Unix/Linux/Mac
        venv_python = venv_dir / "bin" / "python"

    return venv_python


def detect_local_chrome() -> bool:
    """Detect whether a local Chrome/Chromium/Edge is available on this host.

    Used both to pick the query backend (ask_question.py vs ask_cdp.py) and to
    decide whether first-time setup needs to install a browser at all — CDP
    mode connects to the host's browser and never launches its own.
    """
    _system = platform.system()
    if _system == 'Darwin':
        return (
            Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome').exists()
            or Path('/Applications/Chromium.app/Contents/MacOS/Chromium').exists()
            or Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge').exists()
            or bool(shutil.which('google-chrome'))
            or bool(shutil.which('chromium'))
        )
    elif _system == 'Windows':
        return (
            Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe').exists()
            or Path(r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe').exists()
            or bool(shutil.which('chrome'))
        )
    else:  # Linux / other Unix
        return (
            Path('/opt/google/chrome/chrome').exists()
            or bool(shutil.which('google-chrome'))
            or bool(shutil.which('google-chrome-stable'))
            or bool(shutil.which('chromium'))
            or bool(shutil.which('chromium-browser'))
        )


def ensure_venv(install_browser: bool = True):
    """Ensure virtual environment exists.

    install_browser: whether first-time setup should install a local Chrome for
    Patchright. Pass False when CDP mode will be used (no local Chrome found) —
    that backend never launches its own browser, so installing one is wasted
    work and can fail needlessly in restricted containers.
    """
    skill_dir = Path(__file__).parent.parent
    venv_dir = skill_dir / ".venv"
    setup_script = skill_dir / "scripts" / "setup_environment.py"

    # Check if venv exists
    if not venv_dir.exists():
        print("🔧 First-time setup: Creating virtual environment...")
        print("   This may take a minute...")

        # Run setup with system Python
        cmd = [sys.executable, str(setup_script)]
        if not install_browser:
            cmd.append('--skip-browser-install')
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print("❌ Failed to set up environment")
            sys.exit(1)

        print("✅ Environment ready!")

    return get_venv_python()


def main():
    """Main runner"""
    if len(sys.argv) < 2:
        print("Usage: python run.py <script_name> [args...]")
        print("\nAvailable scripts:")
        print("  ask_question.py    - Query NotebookLM")
        print("  notebook_manager.py - Manage notebook library")
        print("  session_manager.py  - Manage sessions")
        print("  auth_manager.py     - Handle authentication")
        print("  cleanup_manager.py  - Clean up skill data")
        sys.exit(1)

    script_name = sys.argv[1]
    script_args = sys.argv[2:]

    # Handle both "scripts/script.py" and "script.py" formats
    if script_name.startswith('scripts/'):
        # Remove the scripts/ prefix if provided
        script_name = script_name[8:]  # len('scripts/') = 8

    # Ensure .py extension
    if not script_name.endswith('.py'):
        script_name += '.py'

    # Detect once up front: drives both backend selection and first-time setup
    # (CDP mode never launches its own browser, so setup can skip installing one).
    chrome_found = detect_local_chrome()

    # Auto-select query backend based on Chrome/Chromium availability:
    # - Chrome/Chromium installed (native Mac/Linux/Windows) → ask_question.py (launches own browser)
    # - Not found (Docker etc.)                              → ask_cdp.py (connects to host browser via CDP)
    if script_name == 'ask_question.py' and not chrome_found:
        print("⚙️  未检测到 Chrome/Chromium — 自动切换到 CDP 模式 (ask_cdp.py)")
        print("   请确保宿主浏览器已以 --remote-debugging-port=9222 启动。")
        script_name = 'ask_cdp.py'

    # Get script path
    skill_dir = Path(__file__).parent.parent
    script_path = skill_dir / "scripts" / script_name

    if not script_path.exists():
        print(f"❌ Script not found: {script_name}")
        print(f"   Working directory: {Path.cwd()}")
        print(f"   Skill directory: {skill_dir}")
        print(f"   Looked for: {script_path}")
        sys.exit(1)

    # Ensure venv exists and get Python executable
    venv_python = ensure_venv(install_browser=chrome_found)

    # Build command
    cmd = [str(venv_python), str(script_path)] + script_args

    # Run the script: On Unix, replace current process directly so PID and signals map 1:1
    if os.name != 'nt':
        try:
            os.execv(str(venv_python), cmd)
        except Exception:
            pass  # Fallback to subprocess if execv fails

    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()