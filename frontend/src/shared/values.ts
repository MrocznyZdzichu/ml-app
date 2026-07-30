export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export function formatOptionalDateTime(value: string) {
  return value
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(new Date(value))
    : "—";
}

export function shortIdOrUnknown(value: string) {
  return value ? value.slice(0, 8) : "unknown";
}
