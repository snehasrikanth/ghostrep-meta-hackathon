/** Optional examples only. Never a recording, personal reference, or analysis input. */
const DEMOS: Record<string, { src: string; title: string; description: string }> = {
  barbell_squat: {
    src: "/demos/squat-example.mp4",
    title: "Squat demo",
    description: "Example movement with shoulder-held weights; equipment may differ from your workout. This is a visual reminder, not your personal reference or a standard of ideal technique.",
  },
};

export function exerciseDemo(exerciseId: string) {
  return Object.hasOwn(DEMOS, exerciseId) ? DEMOS[exerciseId] : null;
}
