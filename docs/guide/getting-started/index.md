# Getting Started

## Environment Setup

### 2.1.1 System requirements

To use AmritaSense, you need:

- Python 3.10 or later (up to 3.14)
- A Python package manager
- Reasonable system resources, such as a 1.8GHz CPU and 1GB RAM or higher

### 2.1.2 Supported Python versions

AmritaSense officially supports Python 3.10 through 3.13. It may work on other versions, but these are the tested and recommended releases.

### 2.1.3 Dependency installation

We recommend using a virtual environment for development. You can use tools like `uv` or `pdm`. The example below uses `uv`.

```bash
uv init
uv venv
uv add amrita-sense
```

Install AmritaSense with pip:

```bash
pip install amrita-sense
```

Or if you are using the source code directly:

```bash
git clone https://github.com/AmritaBot/AmritaSense.git
cd AmritaSense
pip install -e .
```
