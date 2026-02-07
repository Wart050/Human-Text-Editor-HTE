# Human Text Editor (HTE)

Human Text Editor simulates realistic typing into any application, with both human-like and ultra-fast bot modes.

## Features

- **Fresh Type** and **Replace Type** modes
- Human-like timing, pauses, and typo simulation
- **Bot** mode for instant, no-pause typing
- Diff preview for replace edits
- Global hotkeys (F9–F12 by default)
- Settings and text persistence via `hte_settings.json`

## Setup

- Python 3.10+ recommended
- Install dependencies:

```bash
pip install -r requirements.txt
```

## Run

```bash
python human_editor.py
```

## Download & Install (Windows)

The easiest way is to grab the installer from **Releases** and run it.
See `INSTALL.md` for quick steps.

## Hotkeys

- **Start**: F9
- **Pause/Resume**: F10
- **Skip**: F11
- **Stop**: F12

You can change hotkeys from the ℹ button in the app.

## Build (optional)

If you use PyInstaller, `build_exe.py` and `HumanTextEditor.spec` are included for packaging.
For a full Windows installer, run:

```bash
scripts\build_installer.bat
```

## License

GPL-3.0-or-later. See `LICENSE`.
