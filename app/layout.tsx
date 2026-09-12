import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FADS Road Response",
  description: "Report road damage and track a coordinated maintenance response.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
