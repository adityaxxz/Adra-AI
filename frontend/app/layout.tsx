import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Adra-AI - AI-Powered Project Generation",
  description: "Transform your ideas into production-ready code with AI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
          {children}
        </div>
      </body>
    </html>
  );
}
