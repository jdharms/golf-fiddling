# NES Open Tournament Golf Tools

Tools for reverse engineering and editing NES Open Tournament Golf ROM data.

## Requirements

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) package manager

## Setup

### Linux / macOS

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone git@github.com:jdharms/golf-fiddling.git
cd golf-fiddling

# Install dependencies
uv sync
```

### Windows

```powershell
# Install uv (if not already installed)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Clone the repository
git clone git@github.com:jdharms/golf-fiddling.git
cd golf-fiddling

# Install dependencies
uv sync
```

## Project Overview

The codebase is organized into three main packages:

- **golf/** - Shared library for ROM reading, decompression, NES graphics, and data formats
- **editor/** - Interactive Pygame-based course editor for modifying hole layouts
- **tools/** - Command-line utilities for extraction, analysis, and visualization

## Available Commands

| Command | Description |
|---------|-------------|
| `golf-editor` | Launch the interactive course editor |
| `golf-dump <rom> <output_dir>` | Extract course data from ROM to JSON files |
| `golf-write <rom> <course_dir>` | Write course data from JSON back to ROM |
| `golf-analyze <course_dir>` | Analyze hole data patterns and statistics |
| `golf-visualize <tileset> <hole.json>` | Render a hole as a PNG image |
| `golf-expand-dict <meta.json>` | Expand dictionary codes into transition sequences |
| `golf-hex2bin` | Convert hex string to binary file |

### Example Workflow

```bash
# Extract all courses from ROM
golf-dump nes_open_us.nes courses/

# Edit a hole using the course editor
golf-editor courses/japan/hole_01.json

# Write edited course back to ROM
golf-write nes_open_us.nes courses/japan/ -o modified.nes
```

## Running Tests

```bash
pytest
```
