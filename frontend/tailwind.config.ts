import type { Config } from "tailwindcss";

// Colours point at the CSS variables in app/globals.css, so every class follows the light/dark
// theme (<html data-theme>). Prefer these over literal hex values in components.
const config: Config = {
  darkMode: ["selector", '[data-theme="dark"]'],
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        canvas: "var(--bg-base)",
        surface: "var(--bg-surface)",
        elevated: "var(--bg-elevated)",
        subtle: "var(--bg-hover)",
        line: "var(--border)",
        fg: {
          DEFAULT: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          muted: "var(--text-muted)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          solid: "var(--accent-solid)",
          soft: "var(--accent-light)",
        },
        success: "var(--success)",
        warning: "var(--warning)",
        danger: "var(--danger)",
        info: "var(--info)",
      },
      borderColor: {
        DEFAULT: "var(--border)",
        line: "var(--border)",
        "line-hover": "var(--border-hover)",
      },
    },
  },
  plugins: [],
};
export default config;
