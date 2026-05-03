import { defineConfig } from "vitepress";
import { withMermaid } from "vitepress-plugin-mermaid";

// https://vitepress.dev/reference/site-config
export default withMermaid({
  lastUpdated: true,
  ignoreDeadLinks: true,
  sitemap: {
    hostname: "https://sense.amritabot.com",
  },
  locales: {
    root: {
      label: "English",
      lang: "en-US",
      title: "AmritaSense - Next-Gen AI Agent Framework",
      description:
        "AmritaSense is a lightweight, high-performance Python framework for building AI agents with streaming output, tool integration, MCP support, and event-driven architecture. Perfect for LLM-based applications.",
      head: [
        // Icon
        [
          "link",
          {
            rel: "icon",
            href: "/Amrita.png",
          },
        ],
        // SEO Meta Tags
      ],
      themeConfig: {
        // https://vitepress.dev/reference/default-theme-config
        siteTitle: "Amrita Sense Docs",
        nav: [
          { text: "Home", link: "/" },
          { text: "Start", link: "/guide/introduction" },
        ],
        logo: "/Amrita.png",

        sidebar: [],
        footer: {
          message: `LGPL V2 License`,
          copyright: `© Amrita 2025-${new Date().getFullYear()}`,
        },
        socialLinks: [
          { icon: "github", link: "https://github.com/AmritaBot/AmritaSense" },
        ],
      },
    },
    zh: {
      label: "简体中文",
      lang: "zh-CN",
      title: "AmritaSense - 下一代 AI 智能体框架",
      description:
        "AmritaSense 是一个轻量级、高性能的 Python 框架，用于构建具有流式输出、工具集成、MCP 支持和事件驱动架构的 AI 智能体。适用于基于 LLM 的应用开发。",
      head: [
        [
          "link",
          {
            rel: "icon",
            href: "/Amrita.png",
          },
        ],
        // SEO Meta Tags
      ],
      themeConfig: {
        // https://vitepress.dev/reference/default-theme-config
        siteTitle: "Amrita Sense 文档",
        nav: [
          { text: "首页", link: "/zh/" },
          { text: "开始", link: "/zh/guide/introduction" },
        ],
        logo: "/Amrita.png",

        sidebar: [
          
        ],
        footer: {
          message: `LGPL V2 许可证(一些内容可能没有完全翻译成中文，请以英文文档为准。)`,
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
    class: "mermaid my-class", // set additional css classes for parent container
  },
});
