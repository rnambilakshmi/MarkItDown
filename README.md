# MarkItDown GUI

A minimalist drag-and-drop desktop app for [MarkItDown](https://github.com/microsoft/markitdown), Microsoft's tool for converting files (PDF, Word, PowerPoint, Excel, images, HTML, and more) to Markdown.

Drop a file on the window (or click to browse), and it's converted to `.md` using the `markitdown` CLI. No web upload, no account — everything runs locally on your machine.

## Files

- `markitdown_gui.py` — the app
- `Run MarkItDown GUI.command` — double-click launcher (macOS)

## Requirements

- Python 3.9+
- [MarkItDown](https://github.com/microsoft/markitdown) installed and available on your PATH
- Tkinter (see platform notes below — sometimes needs a separate install)
- *(Optional, for drag-and-drop)* the `tkinterdnd2` package

## Installation

**1. Install MarkItDown** (if you haven't already):

```bash
pipx install markitdown
# or: pip install markitdown
```

**2. Make sure Tkinter is available.**

Tkinter ships with the standard Python installer from python.org, but some package managers split it out separately:

- **macOS with Homebrew Python:**
  ```bash
  brew install python-tk
  ```
- **Debian/Ubuntu:**
  ```bash
  sudo apt install python3-tk
  ```
- **Windows / python.org installer:** included by default, nothing to do.

**3. Install drag-and-drop support** (optional but recommended):

```bash
pip install tkinterdnd2 --break-system-packages
```

(Drop the `--break-system-packages` flag if you're installing inside a virtual environment.)

Without this package, the app still works fully via the "Browse Files..." button — you just won't be able to drag files onto the window.

## Usage

**macOS:** double-click `Run MarkItDown GUI.command`.

**Any platform:**

```bash
python3 markitdown_gui.py
```

Then either drag files onto the window, or click the drop zone / "Browse Files..." to pick files manually.

## Where files are saved

By default, each converted file is saved as `<original-name>.md` **in the same folder as the original file**. You can switch to a fixed custom output folder from within the app (radio button + "Choose folder..."). The active save location is always shown at the top of the window, and the full path of every converted file is logged after conversion. If a `.md` file with the same name already exists, it's overwritten.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named '_tkinter'` | Tkinter isn't installed for your Python — see step 2 above. |
| "markitdown was not found on this system's PATH" (shown in the app) | Run `pipx install markitdown`, then restart the app. |
| Drag-and-drop area says a package is missing | Run `pip install tkinterdnd2` (step 3 above). |
| A specific file fails to convert | Check the log in the app — it shows the underlying `markitdown` error for that file (e.g. unsupported format, missing optional dependency such as `markitdown[pdf]`). |

## How it works

The app is a thin GUI wrapper: for each file you drop in, it runs

```bash
markitdown <input-file> -o <output-file>.md
```

and reports success/failure with the full output path. No file contents are sent anywhere — conversion happens entirely via your local `markitdown` installation.

## License

MIT — use, modify, and share freely.
