import { defineConfig } from "vitepress";
import { withMermaid } from "vitepress-plugin-mermaid";

export default withMermaid({
  lastUpdated: true,
  ignoreDeadLinks: true,
  sitemap: {
    hostname: "https://sense.amritabot.com",
  },
  themeConfig: {
    search: {
      provider: "local",
    },
  },
  head: [
    ["link", { rel: "icon", href: "/Amrita.png" }],
    [
      "meta",
      {
        name: "keywords",
        content:
          "workflow engine, python, agent, AI, LLM, orchestration, instruction set, control flow, lightweight, high-performance, async",
      },
    ],
    ["meta", { name: "author", content: "Project.Amrita" }],
    [
      "meta",
      {
        property: "og:title",
        content: "AmritaSense - General-Purpose Workflow Orchestration Engine",
      },
    ],
    [
      "meta",
      {
        property: "og:description",
        content:
          "A lightweight, high-performance Python engine for orchestrating any asynchronous task with a focus on explicit control flow. It provides assembly-like instructions for precise workflow management.",
      },
    ],
    ["meta", { property: "og:type", content: "website" }],
    ["meta", { name: "twitter:card", content: "summary" }],
    [
      "meta",
      {
        name: "twitter:title",
        content: "AmritaSense - General-Purpose Workflow Orchestration Engine",
      },
    ],
    [
      "meta",
      {
        name: "twitter:description",
        content:
          "A lightweight, high-performance Python engine for orchestrating any asynchronous task with a focus on explicit control flow. It provides assembly-like instructions for precise workflow management.",
      },
    ],
  ],
  locales: {
    root: {
      label: "English",
      lang: "en-US",
      title: "AmritaSense - General-Purpose Workflow Orchestration Engine",
      description:
        "A lightweight, high-performance Python engine for orchestrating any asynchronous task with a focus on explicit control flow. It provides assembly-like instructions for precise workflow management.",
      themeConfig: {
        siteTitle: "Amrita Sense Docs",
        nav: [
          { text: "Home", link: "/" },
          { text: "Start", link: "/guide/introduction/" },
        ],
        logo: "/Amrita.png",
        sidebar: [
          {
            text: "Introduction",
            collapsed: false,
            items: [
              { text: "Overview", link: "/guide/introduction/" },
              {
                text: "Key Features",
                link: "/guide/introduction/key-features",
              },
            ],
          },
          {
            text: "Getting Started",
            collapsed: false,
            items: [
              { text: "Install", link: "/guide/getting-started/" },
              {
                text: "Minimal Example",
                link: "/guide/getting-started/minimal-example",
              },
              {
                text: "Basic Example",
                link: "/guide/getting-started/basic-example",
              },
            ],
          },
          {
            text: "Core Concepts",
            collapsed: false,
            items: [
              {
                text: "Composition & Execution",
                link: "/guide/concepts/compose_and_exec",
              },
              {
                text: "Addressing & Data Structures",
                link: "/guide/concepts/addressing_and_data",
              },
              { text: "Flow Control", link: "/guide/concepts/flow_control" },
              {
                text: "Execution & Interrupt",
                link: "/guide/concepts/exec_and_interrupt",
              },
            ],
          },
          {
            text: "Advanced",
            collapsed: false,
            items: [
              {
                text: "Dependency Injection",
                link: "/guide/advanced/dependency_injection",
              },
              {
                text: "Event System",
                link: "/guide/advanced/event_system",
              },
              {
                text: "Locating & Scope",
                link: "/guide/advanced/locating_and_space",
              },
              {
                text: "Calling Subroutines",
                link: "/guide/advanced/child_node",
              },
              {
                text: "External Interrupt",
                link: "/guide/advanced/external_interrupt",
              },
              {
                text: "Built-in Instruction Set",
                items: [
                  {
                    text: "Conditional Branch (IF/ELIF/ELSE)",
                    link: "/guide/advanced/built-in_instruction_set/if_clause",
                  },
                  {
                    text: "Loop Control (WHILE/DO-WHILE)",
                    link: "/guide/advanced/built-in_instruction_set/while_clause",
                  },
                  {
                    text: "Call & Transfer Instructions (GOTO/CALL)",
                    link: "/guide/advanced/built-in_instruction_set/jump_clause",
                  },
                  {
                    text: "Sentinel Instructions (NOP/INTERRUPT)",
                    link: "/guide/advanced/built-in_instruction_set/sentinel_clause",
                  },
                  {
                    text: "Exception Handling (TRY/CATCH/THEN/FIN)",
                    link: "/guide/advanced/built-in_instruction_set/try_clause",
                  },
                  {
                    text: "Context Snapshot & Interrupt Transfer (PUSH_CONTEXT/INTERRUPT_INTO)",
                    link: "/guide/advanced/built-in_instruction_set/context_clause",
                  },
                ],
              },
              { text: "Custom Nodes", link: "/guide/advanced/custom_node" },
              {
                text: "Custom Instructions",
                link: "/guide/advanced/custom_instruction",
              },
              { text: "Unsafe Features", link: "/guide/advanced/unsafe" },
            ],
          },
          {
            text: "Integration & Practice",
            items: [
              {
                text: "Inline Workflows",
                link: "/guide/practice/inline-workflow",
              },
              {
                text: "Manual Stack Management",
                link: "/guide/practice/manual-stack-management",
              },
              {
                text: "Subgraph Isolation",
                link: "/guide/practice/subgraph-isolation",
              },
              {
                text: "Batch Concurrent Invocation",
                link: "/guide/practice/batch-run",
              },
              {
                text: "CLCA Design Pattern",
                link: "/guide/practice/clca-design-pattern",
              },
              {
                text: "Interrupt Routine & Return",
                link: "/guide/practice/interrupt-routine",
              },
              {
                text: "REPL Debugging",
                link: "/guide/practice/repl-debugging",
              },
              { text: "Under Construction..." },
            ],
          },
          {
            text: "API Reference",
            items: [
              { text: "Core Node Classes", link: "/reference/api/core-nodes" },
              { text: "Runtime System", link: "/reference/api/runtime" },
              { text: "Type System", link: "/reference/api/types" },
              { text: "Exception System", link: "/reference/api/exceptions" },
              {
                text: "Self-Compile Instructions",
                link: "/reference/api/self-compile",
              },
              {
                text: "SuspendObjectStream",
                link: "/reference/api/suspend-object-stream",
              },
            ],
          },
          { text: "Appendix", link: "/guide/appendix" },
        ],
        footer: {
          message: `Apache 2.0 License`,
          copyright: `© Amrita 2025-${new Date().getFullYear()}`,
        },
        socialLinks: [
          { icon: "github", link: "https://github.com/AmritaBot/AmritaSense" },
          { icon: "discord", link: "https://discord.gg/byAD3sbjjj" },
        ],
      },
    },
    zh: {
      label: "简体中文",
      lang: "zh-CN",
      title: "AmritaSense - 通用工作流编排引擎",
      description:
        "一个轻量、高性能的Python通用工作流引擎。专注显式控制流，提供汇编级指令实现精确的异步任务编排。",
      head: [["link", { rel: "icon", href: "/Amrita.png" }]],
      themeConfig: {
        siteTitle: "Amrita Sense 文档",
        nav: [
          { text: "首页", link: "/zh/" },
          { text: "开始", link: "/zh/guide/introduction/" },
        ],
        logo: "/Amrita.png",
        sidebar: [
          {
            text: "介绍",
            collapsed: false,
            items: [
              { text: "概述", link: "/zh/guide/introduction/" },
              { text: "主要特性", link: "/zh/guide/introduction/key-features" },
            ],
          },
          {
            text: "快速开始",
            collapsed: false,
            items: [
              { text: "安装", link: "/zh/guide/getting-started/index" },
              {
                text: "最小示例",
                link: "/zh/guide/getting-started/minimal-example",
              },
              {
                text: "基础示例",
                link: "/zh/guide/getting-started/basic-example",
              },
            ],
          },
          {
            text: "概念理解",
            collapsed: false,
            items: [
              {
                text: "编排与运行",
                link: "/zh/guide/concepts/compose_and_exec",
              },
              {
                text: "寻址与数据结构",
                link: "/zh/guide/concepts/addressing_and_data",
              },
              { text: "流程控制", link: "/zh/guide/concepts/flow_control" },
              {
                text: "执行与中断",
                link: "/zh/guide/concepts/exec_and_interrupt",
              },
            ],
          },
          {
            text: "进阶",
            collapsed: false,
            items: [
              {
                text: "依赖注入",
                link: "/zh/guide/advanced/dependency_injection",
              },
              {
                text: "事件系统",
                link: "/zh/guide/advanced/event_system",
              },
              {
                text: "定位与空间",
                link: "/zh/guide/advanced/locating_and_space",
              },
              { text: "子节点调用", link: "/zh/guide/advanced/child_node" },
              {
                text: "外部中断",
                link: "/zh/guide/advanced/external_interrupt",
              },
              {
                text: "内置指令集",
                items: [
                  {
                    text: "条件分支 (IF/ELIF/ELSE)",
                    link: "/zh/guide/advanced/built-in_instruction_set/if_clause",
                  },
                  {
                    text: "循环控制 (WHILE/DO-WHILE)",
                    link: "/zh/guide/advanced/built-in_instruction_set/while_clause",
                  },
                  {
                    text: "调用与转移指令 (GOTO/CALL)",
                    link: "/zh/guide/advanced/built-in_instruction_set/jump_clause",
                  },
                  {
                    text: "哨兵指令 (NOP/INTERRUPT)",
                    link: "/zh/guide/advanced/built-in_instruction_set/sentinel_clause",
                  },
                  {
                    text: "异常处理 (TRY/CATCH/THEN/FIN)",
                    link: "/zh/guide/advanced/built-in_instruction_set/try_clause",
                  },
                  {
                    text: "上下文与中断转移 (PUSH_CONTEXT/INTERRUPT_INTO)",
                    link: "/zh/guide/advanced/built-in_instruction_set/context_clause",
                  },
                ],
              },
              { text: "自定义节点", link: "/zh/guide/advanced/custom_node" },
              {
                text: "自定义指令集",
                link: "/zh/guide/advanced/custom_instruction",
              },
              { text: "Unsafe 特性", link: "/zh/guide/advanced/unsafe" },
            ],
          },
          {
            text: "集成与实践",
            items: [
              {
                text: "内联工作流",
                link: "/zh/guide/practice/inline-workflow",
              },
              {
                text: "手动栈空间管理分配",
                link: "/zh/guide/practice/manual-stack-management",
              },
              {
                text: "子图隔离调用",
                link: "/zh/guide/practice/subgraph-isolation",
              },
              {
                text: "节点与分支并发调用",
                link: "/zh/guide/practice/batch-run",
              },
              {
                text: "CLCA 设计模式",
                link: "/zh/guide/practice/clca-design-pattern",
              },
              {
                text: "中断例程与中断返回",
                link: "/zh/guide/practice/interrupt-routine",
              },
              {
                text: "REPL 调试",
                link: "/zh/guide/practice/repl-debugging",
              },
              { text: "正在施工中......" },
            ],
          },
          {
            text: "API参考",
            items: [
              { text: "核心节点类", link: "/zh/reference/api/core-nodes" },
              { text: "运行时系统", link: "/zh/reference/api/runtime" },
              { text: "类型系统", link: "/zh/reference/api/types" },
              { text: "异常系统", link: "/zh/reference/api/exceptions" },
              { text: "自编译指令", link: "/zh/reference/api/self-compile" },
              {
                text: "SuspendObjectStream",
                link: "/zh/reference/api/suspend-object-stream",
              },
            ],
          },
          { text: "附录", link: "/zh/guide/appendix" },
        ],
        footer: {
          message: `Apache 2.0 许可证约束`,
          copyright: `© Amrita 2025-${new Date().getFullYear()}`,
        },
        socialLinks: [
          { icon: "github", link: "https://github.com/AmritaBot/AmritaSense" },
          { icon: "discord", link: "https://discord.gg/byAD3sbjjj" },
        ],
      },
    },
  },
  mermaidPlugin: {
    class: "mermaid my-class",
  },
});
