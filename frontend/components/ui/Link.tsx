"use client";

import NextLink, { useLinkStatus } from "next/link";
import { LoaderCircle } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

function NavigationStatus() {
  const { pending } = useLinkStatus();
  if (!pending) return null;
  return (
    <span
      role="status"
      className="pointer-events-none absolute right-2 top-2 z-10 text-teal"
    >
      <LoaderCircle
        aria-hidden
        className="h-4 w-4 animate-spin motion-reduce:animate-none"
      />
      <span className="sr-only">Opening page…</span>
    </span>
  );
}

export default function Link({
  children,
  className,
  ...props
}: ComponentProps<typeof NextLink>) {
  return (
    <NextLink className={cn("relative", className)} {...props}>
      {children}
      <NavigationStatus />
    </NextLink>
  );
}
