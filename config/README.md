# Config Files (Legacy)

This folder contains legacy configuration files that have been replaced by `pyproject.toml` and `uv`.

## Files:

- **`requirements.txt`** - Old pip dependency list (replaced by `pyproject.toml`)
- **`setup.sh`** - Old manual setup script (replaced by `uv sync`)

## Modern Setup:

Instead of using these files, use:

```bash
# Install all dependencies
uv sync

# Run scripts
uv run python3 script_name.py
```

These files are kept for reference or backwards compatibility with older tools.
