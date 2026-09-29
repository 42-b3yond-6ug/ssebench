import { defineConfig } from 'vitepress'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  title: "SSEBench",
  description: "Software Security Benchmark for AI Code Agents",
  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Guide', link: '/guide/introduction' },
      { text: 'Reference', link: '/reference/project-structure' }
    ],

    sidebar: {
      '/guide/': [
        {
          text: 'Introduction',
          items: [
            { text: 'What is SSEBench?', link: '/guide/introduction' },
            { text: 'Getting Started', link: '/guide/getting-started' },
            { text: 'Architecture', link: '/guide/architecture' }
          ]
        },
        {
          text: 'Configuration',
          items: [
            { text: 'Adding Models', link: '/guide/models' },
            { text: 'Environment Variables', link: '/guide/environment' }
          ]
        },
        {
          text: 'Agent Development',
          items: [
            { text: 'MCP Server', link: '/guide/mcp-server' },
            { text: 'Dialog Protocol', link: '/guide/dialog-protocol' }
          ]
        }
      ],
      '/reference/': [
        {
          text: 'Reference',
          items: [
            { text: 'Project Structure', link: '/reference/project-structure' }
          ]
        }
      ]
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/42-b3yond-6ug/ssebench' }
    ],

    search: {
      provider: 'local'
    },

    footer: {
      message: 'Released under the Apache License 2.0.',
      copyright: 'Copyright 2025-present the SSEBench authors'
    }
  }
})
