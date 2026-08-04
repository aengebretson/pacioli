import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pacioli",
  description: "Open-source financial data and accounting infrastructure.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
