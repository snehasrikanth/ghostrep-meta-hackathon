import { AppShell } from "@/components/layout/AppShell";
import { LoaderCircle } from "lucide-react";

export default function Loading() {
  return (
    <AppShell>
      <div
        role="status"
        className="flex items-center gap-3 py-12 text-base text-white/85"
      >
        <LoaderCircle
          aria-hidden
          className="h-5 w-5 animate-spin text-teal motion-reduce:animate-none"
        />
        Opening your training…
      </div>
    </AppShell>
  );
}
