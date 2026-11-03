import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Sora, Syne } from "next/font/google";
import "./globals.css";

const sora = Sora({
  variable: "--font-sora",
  subsets: ["latin"],
});

const syne = Syne({
  variable: "--font-syne",
  subsets: ["latin"],
  weight: ["600", "700", "800"],
});

const ibm = IBM_Plex_Mono({
  variable: "--font-ibm",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const title = "GhostRep | Your Best Rep Becomes Your Coach";
const description =
  "GhostRep is a personalized fitness coaching app that uses video-based movement analysis, personal reference repetitions, and adaptive feedback to help you understand your training.";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000"),
  title: {
    default: title,
    template: "%s | GhostRep",
  },
  description,
  applicationName: "GhostRep",
  keywords: ["GhostRep", "fitness", "movement analysis", "squat", "coaching"],
  openGraph: {
    title,
    description,
    siteName: "GhostRep",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title,
    description,
  },
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
    apple: [{ url: "/apple-icon" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#07090c",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sora.variable} ${syne.variable} ${ibm.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">{children}</body>
    </html>
  );
}
