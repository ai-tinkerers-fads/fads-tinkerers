import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "FADS · Road support",
  description:
    "Report road damage or log a repair question with our voice intake assistant.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
