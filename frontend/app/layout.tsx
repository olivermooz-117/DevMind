import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DevMind | AI Engineering Workbench",
  description:
    "A private, local-first AI engineering workbench for understanding, searching, and exploring codebases.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
