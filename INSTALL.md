# Install Human Text Editor (Windows)

## Option A — Download installer (recommended)

1. Open the GitHub repo.
2. Go to **Releases**.
3. Download **HumanTextEditor-Setup.exe**.
4. Run the installer and launch the app.

## Option B — Build the installer yourself

Prerequisites:

- Python 3.10+
- Inno Setup 6

Steps:

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Build the installer:

```bash
scripts\build_installer.bat
```

The installer will be created in `dist\installer`.
