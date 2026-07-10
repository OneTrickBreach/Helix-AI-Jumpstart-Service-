import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17201a",
        field: "#f6f7f3",
        line: "#d7ddcf",
        good: "#1b7f45",
        bad: "#b42318",
        warn: "#a15c07",
      },
      boxShadow: {
        soft: "0 18px 50px rgba(31, 41, 35, 0.08)",
      },
    },
  },
  plugins: [],
} satisfies Config;
