import nextConfig from "eslint-config-next";

export default [
  {
    ignores: [
      "**/.next/**",
      "**/node_modules/**",
      "**/out/**",
      "**/build/**",
      "**/coverage/**",
      "**/dist/**",
      "**/*.tsbuildinfo",
      "**/next-env.d.ts",
    ],
  },
  ...nextConfig,
];
