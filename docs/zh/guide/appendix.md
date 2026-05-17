# 附录和资源

## 9.1 术语表和术语

### 9.1.1 Workflow（工作流）

在 AmritaSense 中，工作流是由节点（Node）按特定顺序编排而成的异步执行流。它不是一个静态的图结构，而是一个可被解释器步进执行、支持中断与跳转的指令序列。

### 9.1.2 Node（节点）

工作流的最小执行单元。任何被 `@Node()` 装饰的 Python 函数或协程都是一个节点。节点是原子的——它要么完全执行，要么完全不执行。条件判断、循环体、异常处理器，一切都是节点。

### 9.1.3 PointerVector（指针向量）

AmritaSense 的核心寻址数据结构。它是一个变长整数数组，每个维度对应一个嵌套层级，该维度上的数值表示当前层级内的偏移索引。在解释器主循环中，`PointerVector` 扮演程序计数器（PC）的角色，始终指向当前正在执行的节点。

### 9.1.4 Bubble（气泡作用域）

由括号 `()` 包裹的节点组在编译后形成的独立地址空间。每个 Bubble 拥有独立的 `near` 地址空间，内部的跳转操作不会影响外层。Bubble 是 AmritaSense 实现作用域隔离和数据封装的底层机制。

### 9.1.5 Instruction Set（指令集）

AmritaSense 提供的一套完备的控制流原语，包括 `IF/ELIF/ELSE`（条件分支）、`WHILE/DO-WHILE`（循环）、`GOTO`（无条件跳转）、`CALL`（子程序调用）、`TRY/CATCH/THEN/FIN`（异常处理）、`NOP`（哨兵）和 `INTERRUPT`（强制终止）。所有指令在编译期展开为底层节点组合，运行时通过指针跳转完成。

### 9.1.6 Self-Compile Instruction（自编译指令）

实现 `SelfCompileInstruction` 接口的指令类。它们在 `render()` 阶段通过 `extract()` 方法自动展开为标准的 `NodeCompose` 结构。内置指令和开发者自定义指令都基于这一机制，实现了编译期优化和运行时的零开销。

### 9.1.7 Interrupt（流程中断）

AmritaSense 提供的协作式中断机制。工作流在指定标记点主动挂起，将控制权交还给外部系统。外部系统可以在此窗口期内检查状态、修改变量，然后通过 `resume()` 恢复执行。这是构建调试器和外部监控系统的基础能力。

### 9.1.8 Depends（依赖注入）

借鉴 FastAPI 的依赖注入模式。节点通过在函数签名中声明 `Depends(factory)` 来声明自己需要的资源。AmritaSense 的依赖解析系统支持并发解析、运行时注入和类型匹配。若工厂函数返回 `None`，工作流将直接终止。

### 9.1.9 Alias（别名）

通过 `ALIAS` 指令为节点绑定的全局唯一符号名。编译期注册到 `alias2vector_map`，供 `GOTO` 和 `CALL` 在运行时查表解析。这是 AmritaSense 符号寻址体系的基础。

### 9.1.10 Subprogram（子程序）

通过 `ARCHIVED_NODES` 指令定义的、被 `SubprogramJumpNode` 跳过、仅通过 `CALL` 或外部注入访问的节点序列。子程序可以存储中断处理逻辑、调试工具或可复用的功能模块，正常执行流不受其存在的影响。

### 9.1.11 其他核心术语

- **解释锁（Interpret Lock）**：`aiologic.Lock` 实例，保证每次只有一个节点在执行，是外部安全调用的互斥基础
- **跳转标记（Jump Mark）**：`_jump_marked` 标志，为 `True` 时解释器跳过常规的指针推进步骤，下一轮从跳转目标开始
- **异常穿透（Exception Penetration）**：通过 `exception_ignored` 标记的异常不会被任何 `CATCH` 块捕获，直达顶层处理器
- **Call Stack（调用栈）**：`Stack[PointerVector]`，管理子程序调用的返回地址

### 9.1.12 缩写词

- **API**：Application Programming Interface（应用程序编程接口）
- **DI**：Dependency Injection（依赖注入）
- **PC**：Program Counter（程序计数器）
- **JSON**：JavaScript Object Notation（JavaScript 对象表示法）
- **HTTP**：Hypertext Transfer Protocol（超文本传输协议）
- **LGPL**：GNU Lesser General Public License（GNU 宽通用公共许可证）
- **ISA**：Instruction Set Architecture（指令集架构）

## 9.2 项目资源

### 9.2.1 GitHub 仓库

- **AmritaSense 仓库**：[https://github.com/AmritaBot/AmritaSense](https://github.com/AmritaBot/AmritaSense)
- **AmritaCore 仓库**：[https://github.com/AmritaBot/AmritaCore](https://github.com/AmritaBot/AmritaCore)
- **问题报告**：在对应仓库中提交错误报告和功能请求
- **拉取请求**：欢迎通过 PR 贡献代码

### 9.2.2 官方网站

- **AmritaSense 文档**：[https://sense.amritabot.com](https://sense.amritabot.com)（即此页面）
- **AmritaCore 文档**：[https://core.amritabot.com](https://core.amritabot.com)
- **综合指南与教程**：两个文档站分别提供了完整的指南和 API 参考

### 9.2.3 贡献指南

欢迎对 AmritaSense 做出贡献。以下是贡献流程：

1. **Fork 仓库**：创建项目的个人副本
2. **创建分支**：在新分支中进行更改
3. **编写测试**：确保更改不破坏现有功能
4. **更新文档**：保持文档与代码同步
5. **提交拉取请求**：描述更改内容并提交审核

**代码风格指南**：

- 遵循 PEP 8 Python 风格指南
- 为所有公共函数和类编写文档字符串
- 为所有函数参数和返回值使用类型提示
- 保持函数聚焦和简洁
- 核心业务逻辑必须由人工编写（详见仓库中的 AIGC 政策）

更多信息请参考各项目仓库中的 `CONTRIBUTING.md` 文件。

### 9.2.4 许可证

- **AmritaSense**：根据 **LGPL V2** 许可证发布
- **AmritaCore**：根据 **MIT** 许可证发布

有关完整许可证文本，请参阅各仓库中的 `LICENSE` 文件。

## 9.3 社区和支持

### 9.3.1 讨论与反馈

- **Discord 服务器**：[https://discord.gg/byAD3sbjjj](https://discord.gg/byAD3sbjjj)
- **QQ 群**：1006893368
- **GitHub Discussions**：在仓库的讨论板块中参与技术讨论

### 9.3.2 问题提交

报告问题时请遵循以下步骤：

1. 搜索现有问题以避免重复
2. 提供清晰、描述性的标题
3. 包含完整的重现步骤和代码片段
4. 指定运行环境（操作系统、Python 版本、库版本）

### 9.3.3 行为准则

Amrita 社区遵循贡献者盟约行为准则：

- **尊重他人**：无论背景如何，都应尊重每个人
- **建设性**：提供建设性的反馈和建议
- **包容**：欢迎来自各种背景的人
- **关注质量**：努力提高项目质量

## 9.4 设计哲学与相关资源

### 9.4.1 设计哲学

- **"一切皆是节点"**：条件判断、循环体、异常处理器——它们都是 `Node` 的实例
- **"指令替代图"**：工作流是线性节点数组上的非线性执行流，跳转即指针改写
- **"极简即真理"**：用最少的代码实现完备的控制流

### 9.4.2 相关技术资源

- **Python 官方文档**：[https://docs.python.org/3/](https://docs.python.org/3/)
- **Python asyncio 文档**：[https://docs.python.org/3/library/asyncio.html](https://docs.python.org/3/library/asyncio.html)
- **AmritaCore 文档**：[https://core.amritabot.com](https://core.amritabot.com)（Amrita 生态的上层基础设施）
- **VitePress 文档**：[https://vitepress.dev/](https://vitepress.dev/)（本站构建工具）

### 9.4.3 推荐阅读

- **"流程图何必是图"**——理解 AmritaSense 设计理念的核心文章
- **"KISS 原则"**：Keep It Simple, Stupid——AmritaSense 遵循的设计哲学
- **"Unix 哲学"**：小、专注、可组合——AmritaSense 的模块化设计基础
