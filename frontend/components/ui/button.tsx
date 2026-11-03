import { LoaderCircle } from "lucide-react";
import { buttonClass } from "@/lib/buttonStyles";
import type { ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "amber";
  loading?: boolean;
  loadingLabel?: string;
};

export function Button({
  className,
  variant = "primary",
  loading = false,
  loadingLabel,
  disabled,
  children,
  ...props
}: Props) {
  return (
    <button
      type="button"
      className={buttonClass(variant, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && (
        <LoaderCircle
          aria-hidden
          className="h-4 w-4 animate-spin motion-reduce:animate-none"
        />
      )}
      {loading && loadingLabel ? loadingLabel : children}
    </button>
  );
}
