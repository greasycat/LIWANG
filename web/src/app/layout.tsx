import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LIWANG 知识助手",
  description: "LIWANG 知识助手",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" data-theme="light">
      <body className="min-h-screen bg-base-200 text-base-content font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
