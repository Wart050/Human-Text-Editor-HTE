import os
import sys
import struct
import subprocess
from pathlib import Path

APP_NAME = "HumanTextEditor"
PROJECT_ROOT = Path(__file__).resolve().parent
ICON_PATH = PROJECT_ROOT / "assets" / "icon.ico"
SCRIPT_PATH = PROJECT_ROOT / "human_editor.py"


def generate_icon(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    width = 64
    height = 64
    bpp = 32

    # BGRA color (soft blue)
    pixel = bytes([0x4C, 0x7A, 0xF1, 0xFF])
    pixels = pixel * (width * height)

    mask_row_bytes = ((width + 31) // 32) * 4
    mask = b"\x00" * (mask_row_bytes * height)

    biSize = 40
    biWidth = width
    biHeight = height * 2
    biPlanes = 1
    biBitCount = bpp
    biCompression = 0
    biSizeImage = len(pixels)
    biXPelsPerMeter = 0
    biYPelsPerMeter = 0
    biClrUsed = 0
    biClrImportant = 0

    bmp_header = struct.pack(
        "<IIIHHIIIIII",
        biSize,
        biWidth,
        biHeight,
        biPlanes,
        biBitCount,
        biCompression,
        biSizeImage,
        biXPelsPerMeter,
        biYPelsPerMeter,
        biClrUsed,
        biClrImportant,
    )

    image_data = bmp_header + pixels + mask

    # ICONDIR
    icon_dir = struct.pack("<HHH", 0, 1, 1)

    # ICONDIRENTRY
    entry = struct.pack(
        "<BBBBHHII",
        width if width < 256 else 0,
        height if height < 256 else 0,
        0,  # color count
        0,  # reserved
        1,  # planes
        bpp,
        len(image_data),
        6 + 16,  # offset
    )

    with open(path, "wb") as f:
        f.write(icon_dir)
        f.write(entry)
        f.write(image_data)


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        return
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def ensure_keyboard():
    try:
        import keyboard  # noqa: F401
        return
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "keyboard"])


def ensure_venv_python():
    """If a local .venv exists, re-run this script with that interpreter."""
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        return
    current = Path(sys.executable).resolve()
    target = venv_python.resolve()
    if current != target:
        args = [str(target), str(Path(__file__).resolve())] + sys.argv[1:]
        raise SystemExit(subprocess.call(args, cwd=str(PROJECT_ROOT)))


def build():
    ensure_venv_python()

    if not ICON_PATH.exists():
        generate_icon(str(ICON_PATH))

    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Script not found: {SCRIPT_PATH}")

    ensure_pyinstaller()
    ensure_keyboard()

    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconsole",
        "--onefile",
        "--name",
        APP_NAME,
        "--icon",
        str(ICON_PATH),
        "--add-data",
        f"{PROJECT_ROOT / 'assets'};assets",
        "--hidden-import",
        "keyboard",
        str(SCRIPT_PATH),
    ]
    subprocess.check_call(args, cwd=str(PROJECT_ROOT))

    exe_path = os.path.join(PROJECT_ROOT, "dist", f"{APP_NAME}.exe")
    if not os.path.exists(exe_path):
        raise FileNotFoundError(f"Build finished but {exe_path} was not found.")
    print(f"Build complete: {exe_path}")


if __name__ == "__main__":
    build()
