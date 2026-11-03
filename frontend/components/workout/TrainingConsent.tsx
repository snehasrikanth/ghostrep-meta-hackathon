"use client";

export function TrainingConsent({
  checked,
  onChange,
  disabled = false,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="mt-5 flex min-h-11 cursor-pointer items-start gap-3 rounded-2xl border border-white/10 bg-black/20 p-4 text-sm leading-6 text-white/85">
      <input
        type="checkbox"
        className="mt-1 h-4 w-4 shrink-0 accent-teal"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        I agree to share my training preferences and recent workout history with
        the coaching service to build a personalized plan. I can review the plan
        before using it.
      </span>
    </label>
  );
}
