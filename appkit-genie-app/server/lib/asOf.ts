/**
 * The data's snapshot date (deploy config as_of_date, passed as LENSS_AS_OF_DATE through app.yaml).
 * One setting: the Command Center, Explorer, account lists and the platform guide all quote it.
 */
const raw = process.env.LENSS_AS_OF_DATE ?? '2026-10-20';
if (!/^\d{4}-\d{2}-\d{2}$/.test(raw) || Number.isNaN(Date.parse(`${raw}T00:00:00Z`))) {
  throw new Error(`LENSS_AS_OF_DATE must be YYYY-MM-DD, got: ${raw}`);
}

/** 2026-10-20 */
export const AS_OF = raw;

/** The snapshot as a SQL literal: DATE '2026-10-20' (validated above, safe to inline). */
export const AS_OF_SQL = `DATE '${raw}'`;

/** 20 October 2026 */
export const AS_OF_LABEL = new Date(`${raw}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
