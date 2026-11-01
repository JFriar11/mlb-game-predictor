export const pct = (value: number) => `${(value * 100).toFixed(1)}%`;
export const number = (value: number, places = 1) => value.toFixed(places);
export function validDate(value: string | null): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T12:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}
export function today(): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const get = (type: string) => parts.find((p) => p.type === type)!.value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}
export function moveDate(value: string, days: number): string {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
export const prettyDate = (value: string) =>
  new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC',
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(`${value}T12:00:00Z`));
export const time = (value: string | Date, full = false) =>
  new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago',
    hour: 'numeric',
    minute: '2-digit',
    ...(full ? ({ month: 'short', day: 'numeric', year: 'numeric' } as const) : {}),
  }).format(new Date(value)) + ' CT';
export function teamName(
  side: 'home' | 'away',
  prediction: import('./contracts').Prediction,
): string {
  // Mutable team identity cannot replace prediction-time identity after a team change.
  const discovery = prediction.latest_discovery;
  const captured = prediction.explanation[`${side}_team_id`];
  if (discovery && (captured === null || captured === discovery[`${side}_team_id`]))
    return discovery[`${side}_team_name`];
  return `${side === 'home' ? 'Home' : 'Away'} team${captured ? ` · MLB ${captured}` : ''}`;
}
