"use client";

import { AppShell } from "@/components/layout/AppShell";
import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";

export default function OnboardingPage() {
  return (
    <AppShell>
      <OnboardingWizard />
    </AppShell>
  );
}
