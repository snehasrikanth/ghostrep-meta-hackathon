"use client";

import { BrandLockup } from "@/components/brand/BrandLockup";
import { GhostRepMark } from "@/components/brand/GhostRepMark";
import { DemoAccountBar } from "@/components/layout/DemoAccountBar";
import { ViewToggle } from "@/components/layout/ViewToggle";
import { buttonClass } from "@/lib/buttonStyles";
import { cn } from "@/lib/cn";
import Link from "@/components/ui/Link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type CSSProperties } from "react";

const links = [
  { href: "/dashboard", label: "Today" },
  { href: "/program", label: "My plan" },
  { href: "/record", label: "Record" },
  { href: "/onboarding", label: "Profile" },
  { href: "/history", label: "Progress" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const headerRef = useRef<HTMLElement>(null);
  const [headerHeight, setHeaderHeight] = useState(64);
  useEffect(() => {
    const header = headerRef.current;
    if (!header) return;
    const observer = new ResizeObserver(() =>
      setHeaderHeight(Math.ceil(header.getBoundingClientRect().height)),
    );
    observer.observe(header);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      className="min-h-screen"
      style={{ "--app-header-height": `${headerHeight}px` } as CSSProperties}
    >
      <header
        ref={headerRef}
        className="sticky top-0 z-40 border-b border-white/8 bg-[#07090c]/80 backdrop-blur-xl"
      >
        <div className="mx-auto flex min-h-16 max-w-6xl items-center justify-between gap-2 px-3 py-2 sm:gap-3 sm:px-5">
          <Link href="/" className="flex min-h-11 shrink-0 items-center rounded-lg" aria-label="GhostRep home">
            <GhostRepMark className="h-7 w-7 sm:hidden" />
            <span className="hidden sm:block"><BrandLockup compact /></span>
          </Link>
          <nav
            aria-label="Main navigation"
            className="flex min-w-0 flex-1 items-center justify-between gap-0 text-xs sm:flex-none sm:gap-1 sm:text-sm"
          >
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={
                  pathname.startsWith(link.href) ? "page" : undefined
                }
                className={cn(
                  "inline-flex min-h-11 min-w-11 items-center justify-center rounded-full px-1 py-2 text-white/80 hover:text-white sm:px-3",
                  pathname.startsWith(link.href) && "bg-white/8 text-white",
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>
          <Link
            href="/start"
            className={buttonClass(
              "secondary",
              "hidden px-4 py-2 sm:inline-flex",
            )}
          >
            Train
          </Link>
          <ViewToggle />
        </div>
        <DemoAccountBar />
      </header>
      <main className="mx-auto w-full max-w-6xl px-5 pt-6 pb-[calc(7rem+env(safe-area-inset-bottom))] sm:pt-8">{children}</main>
    </div>
  );
}
