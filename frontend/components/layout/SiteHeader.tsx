"use client";

import { BrandLockup } from "@/components/brand/BrandLockup";
import { ViewToggle } from "@/components/layout/ViewToggle";
import { buttonClass } from "@/lib/buttonStyles";
import { cn } from "@/lib/cn";
import Link from "next/link";
import { useState } from "react";

const links = [
  { href: "#product", label: "Product" },
  { href: "#how-it-works", label: "How It Works" },
  { href: "#features", label: "Features" },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-white/6 bg-[#07090c]/80 backdrop-blur-xl">
      <div className="mx-auto flex h-[4.25rem] max-w-6xl items-center justify-between px-5">
        <Link href="/" className="rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-teal">
          <BrandLockup compact />
        </Link>
        <nav className="hidden items-center gap-8 text-sm text-white/55 md:flex">
          {links.map((link) => (
            <a key={link.href} href={link.href} className="transition hover:text-white">
              {link.label}
            </a>
          ))}
        </nav>
        <div className="hidden items-center gap-4 md:flex">
          <Link href="/dashboard" className="text-sm text-white/55 transition hover:text-white">
            Dashboard
          </Link>
          <Link href="/start" className={buttonClass("primary", "px-4 py-2")}>
            Start Training
          </Link>
          <ViewToggle />
        </div>
        <button
          type="button"
          className="relative inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/10 md:hidden"
          aria-expanded={open}
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((value) => !value)}
        >
          <span className={cn("absolute h-px w-4 bg-white transition", open ? "rotate-45" : "-translate-y-1")} />
          <span className={cn("absolute h-px w-4 bg-white transition", open ? "-rotate-45" : "translate-y-1")} />
        </button>
      </div>
      {open && (
        <nav className="border-t border-white/6 px-5 py-4 md:hidden">
          <div className="flex flex-col gap-3 text-sm">
            {links.map((link) => (
              <a key={link.href} href={link.href} onClick={() => setOpen(false)} className="py-1 text-white/70">
                {link.label}
              </a>
            ))}
            <Link href="/dashboard" onClick={() => setOpen(false)} className="py-1 text-white/70">
              Dashboard
            </Link>
            <Link href="/start" className={buttonClass("primary", "mt-2 w-full")} onClick={() => setOpen(false)}>
              Start Training
            </Link>
          </div>
        </nav>
      )}
    </header>
  );
}
