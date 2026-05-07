import next from "eslint-config-next/core-web-vitals";

const config = [
  {
    ignores: [".next/", "node_modules/", "next-env.d.ts"],
  },
  ...next,
  {
    files: ["**/*.{ts,tsx}"],
    rules: {
      "@next/next/no-img-element": "off",
    },
  },
];

export default config;
