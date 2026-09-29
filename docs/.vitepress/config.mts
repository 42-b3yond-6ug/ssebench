import { readFileSync } from 'node:fs'
import { defineConfig, type DefaultTheme } from 'vitepress'

const repo = 'https://github.com/42-b3yond-6ug/ssebench'

const version = readFileSync(new URL('../../VERSION', import.meta.url), 'utf8').trim()

const sidebar: DefaultTheme.SidebarItem[] = [
  {
    text: 'Getting started',
    items: [
      { text: 'What is SSEBench?', link: '/getting-started/introduction' },
      { text: 'Try the demo', link: '/getting-started/demo' },
      { text: 'Installation', link: '/getting-started/installation' },
      { text: 'Quickstart', link: '/getting-started/quickstart' },
      { text: 'Troubleshooting', link: '/getting-started/troubleshooting' }
    ]
  },
  {
    text: 'Concepts',
    collapsed: true,
    items: [
      { text: 'Architecture', link: '/concepts/architecture' },
      { text: 'Tasks and datasets', link: '/concepts/tasks-and-datasets' },
      { text: 'Image layers', link: '/concepts/image-layers' },
      { text: 'Sandbox and sidecar', link: '/concepts/sandbox-and-sidecar' },
      { text: 'Difficulty levels', link: '/concepts/difficulty-levels' },
      { text: 'Grading pipeline', link: '/concepts/grading' },
      { text: 'Results format', link: '/concepts/results' },
      { text: 'LiteLLM proxy', link: '/concepts/litellm-proxy' },
      { text: 'Plugins and hooks', link: '/concepts/plugins-and-hooks' },
      { text: 'Integrity model', link: '/concepts/integrity' }
    ]
  },
  {
    text: 'Guides',
    collapsed: true,
    items: [
      { text: 'Add an agent', link: '/guides/add-an-agent' },
      { text: 'Add a model', link: '/guides/add-a-model' },
      { text: 'Add a task', link: '/guides/add-a-task' },
      { text: 'Write a plugin', link: '/guides/write-a-plugin' },
      { text: 'Extension points', link: '/guides/extension-points' }
    ]
  },
  {
    text: 'Dataset',
    collapsed: true,
    items: [
      { text: 'The pilot dataset', link: '/dataset/pilot' },
      { text: 'Dataset manifest', link: '/dataset/manifest' }
    ]
  },
  {
    text: 'Reference',
    collapsed: true,
    items: [
      { text: 'CLI', link: '/reference/cli' },
      { text: 'Environment variables', link: '/reference/environment' },
      { text: 'Configuration files', link: '/reference/configuration' },
      { text: 'MCP server', link: '/reference/mcp-server' },
      { text: 'Dialog protocol', link: '/reference/dialog-protocol' },
      { text: 'Python SDK', link: '/reference/python-sdk' },
      { text: 'Daemon HTTP API', link: '/reference/daemon-api' }
    ]
  },
  {
    text: 'WebUI',
    collapsed: true,
    items: [
      { text: 'Overview', link: '/webui/' },
      { text: 'Launching runs', link: '/webui/launching-runs' },
      { text: 'Watching a run', link: '/webui/run-view' },
      { text: 'Security model', link: '/webui/security' }
    ]
  },
  {
    text: 'Deployment',
    collapsed: true,
    items: [
      { text: 'Local stack', link: '/deployment/compose' },
      { text: 'Kubernetes', link: '/deployment/kubernetes' },
      { text: 'Integrity and egress', link: '/deployment/integrity-and-egress' }
    ]
  },
  {
    text: 'Contributing',
    collapsed: true,
    items: [
      { text: 'How to contribute', link: '/contributing/' },
      { text: 'Project structure', link: '/contributing/project-structure' },
      { text: 'Writing documentation', link: '/contributing/documentation' },
      { text: 'Releasing and versioning', link: '/contributing/releasing' }
    ]
  }
]

export default defineConfig({
  title: 'SSEBench',
  description: 'Software Security Benchmark for AI Code Agents',
  lang: 'en-US',

  // Served from the root of a custom domain on GitHub Pages.
  base: '/',
  cleanUrls: true,

  themeConfig: {
    nav: [
      { text: 'Getting started', link: '/getting-started/introduction', activeMatch: '^/getting-started/' },
      { text: 'Concepts', link: '/concepts/architecture', activeMatch: '^/concepts/' },
      { text: 'Guides', link: '/guides/add-an-agent', activeMatch: '^/guides/' },
      { text: 'Dataset', link: '/dataset/pilot', activeMatch: '^/dataset/' },
      { text: 'Reference', link: '/reference/cli', activeMatch: '^/reference/' },
      {
        text: 'More',
        activeMatch: '^/(webui|deployment|contributing)/',
        items: [
          { text: 'WebUI', link: '/webui/', activeMatch: '^/webui/' },
          { text: 'Deployment', link: '/deployment/compose', activeMatch: '^/deployment/' },
          { text: 'Contributing', link: '/contributing/', activeMatch: '^/contributing/' }
        ]
      },
      {
        text: version,
        items: [
          { text: 'Releases', link: `${repo}/releases` },
          { text: 'Contributing', link: '/contributing/' }
        ]
      }
    ],

    sidebar,

    socialLinks: [{ icon: 'github', link: repo }],

    editLink: {
      pattern: `${repo}/edit/main/docs/:path`,
      text: 'Edit this page on GitHub'
    },

    search: {
      provider: 'local'
    },

    footer: {
      message: 'Released under the Apache License 2.0.',
      copyright: 'Copyright 2025-present the SSEBench authors'
    }
  }
})
