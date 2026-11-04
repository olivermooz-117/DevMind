import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DevMind | Local AI Engineering Workbench",
  description: "A privacy-focused local AI engineering assistant."
};

export default function RootLayout({
  children
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
