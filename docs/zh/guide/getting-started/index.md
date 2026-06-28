# 开始使用

## 环境准备

### 2.1.1 系统要求

要使用 AmritaSense，您需要：

- Python 3.10 或更高版本（最高到 3.15）
- Python 包管理器
- 能够运行Python的设备

### 2.1.2 Python 版本支持

AmritaSense 官方支持从 3.10 到 3.15 的 Python 版本，我们为这些版本添加了测试矩阵。

### 2.1.3 依赖安装

我们推荐您使用我们的项目脚手架`amctl`安装 AmritaSense：

```bash
# 如果没有 amctl，请先安装
# pip install amctl
# 或者使用uv tool
# uv tool install amctl
amctl create
# 选择AmritaSense模板
```

使用uv创建项目：

```bash
mkdir my_awesome_project
cd my_awesome_project
uv init && uv add amrita-sense
```

或者如果您直接使用源代码：

```bash
git clone https://github.com/AmritaBot/AmritaSense.git
cd AmritaSense
pip install -e .
```
