# Getting Started

## Environment Setup

### System requirements

To use AmritaSense, you need:

- Python 3.10 or later (up to 3.15)
- A Python package manager
- Device that can run Python

### Supported Python versions

AmritaSense officially supports Python 3.10 through 3.15, and we maintain a test matrix for these versions.

### Dependency installation

We recommend using our project scaffolding tool `amctl` to install AmritaSense:

```bash
# If you don't have amctl, install it first
# pip install amctl
# Or use uv tool
# uv tool install amctl
amctl create
# Select the AmritaSense template
```

Create a project with uv:

```bash
mkdir my_awesome_project
cd my_awesome_project
uv init && uv add amrita-sense
```

Or if you are using the source code directly:

```bash
git clone https://github.com/AmritaBot/AmritaSense.git
cd AmritaSense
pip install -e .
```
