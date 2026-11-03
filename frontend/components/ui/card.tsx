import { cn } from "@/lib/cn";
import type { HTMLAttributes } from "react";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-[1.5rem] border border-white/8 bg-card/90 shadow-[0_20px_60px_rgba(0,0,0,0.35)]", className)}
      {...props}
    />
  );
}
