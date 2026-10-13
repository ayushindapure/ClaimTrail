import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ClaimTrail — Follow every claim back to its source",
  description: "A research workspace for following claims, exploring archival evidence and reviewing related passages.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
