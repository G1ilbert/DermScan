import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "DermScan",
  description: "AI skin lesion screening for pre-hospital use",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">{children}</body>
    </html>
  );
}
