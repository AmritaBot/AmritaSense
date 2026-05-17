# 开始使用

## 环境准备

### 2.1.1 系统要求

要使用 AmritaSense，您需要：

- Python 3.10 或更高版本（最高到 3.14）
- Python 包管理器
- 足够的性能，例如 1.8Ghz CPU 与 1GB RAM 或更高

### 2.1.2 Python 版本支持

AmritaSense 官方支持从 3.10 到 3.13 的 Python 版本。虽然它可能在其他版本上也能工作，但这些是经过测试和推荐的版本。

### 2.1.3 依赖安装

我们建议使用虚拟环境进行开发，可使用 `uv`、`pdm` 等。这里给出`uv`的示例。

```bash
uv init
uv venv
uv add amrita-sense
```

使用 pip 安装 AmritaSense：

```bash
pip install amrita-sense
```

或者如果您直接使用源代码：

```bash
git clone https://github.com/AmritaBot/AmritaSense.git
cd AmritaSense
pip install -e .
```
