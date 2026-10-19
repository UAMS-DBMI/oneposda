/** Display helpers matching what the Perl timeline showed. */

const ISO_DURATION = /^(-)?P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$/;

/** Seconds in an ISO 8601 duration as pydantic emits it (e.g. "PT1M0.03S"). */
export function parseIsoDuration(value: string): number {
  const match = ISO_DURATION.exec(value);
  if (!match) throw new Error(`not an ISO 8601 duration: ${value}`);
  const [, sign, days, hours, minutes, seconds] = match;
  const total =
    Number(days ?? 0) * 86400 +
    Number(hours ?? 0) * 3600 +
    Number(minutes ?? 0) * 60 +
    Number(seconds ?? 0);
  return sign ? -total : total;
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

/** "HH:MM:SS.ss", the shape Perl rendered from a Postgres interval. */
export function formatDuration(iso: string | null): string {
  if (iso === null) return "";
  const total = parseIsoDuration(iso);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total - hours * 3600 - minutes * 60;
  return `${pad2(hours)}:${pad2(minutes)}:${pad2(Math.floor(seconds))}.${pad2(
    Math.round((seconds % 1) * 100),
  )}`;
}

/** Local "YYYY-MM-DD HH:MM:SS" for an ISO timestamp; empty for null. */
export function formatTimestamp(iso: string | null): string {
  if (iso === null) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return (
    `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ` +
    `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`
  );
}
