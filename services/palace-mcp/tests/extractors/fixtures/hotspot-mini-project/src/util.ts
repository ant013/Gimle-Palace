export function pickLabel(score: number): string {
  if (score < 0) return "invalid";
  if (score < 50) return "low";
  return "high";
}
