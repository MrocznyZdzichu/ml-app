import type { DatasetPreview } from "../api/client";
import {
  columnRoleOptions,
  defaultColumnRole
} from "../analysis/dataRoles";
import type { DataRolesMetadata } from "../analysis/dataRoles";


export function columnRoleLabel(role: string) {
  return columnRoleOptions.find((option) => option.value === role)?.label ?? role;
}

export function columnRoleForColumn(
  column: DatasetPreview["columns"][number],
  rolesMetadata: DataRolesMetadata
) {
  return rolesMetadata.column_roles[column.name] ?? defaultColumnRole(column.type);
}

export function roundNumber(value: number) {
  return Number(value.toFixed(6));
}


export function valueToSearchText(value: unknown) {
  return displayValue(value).toLowerCase();
}

export function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "null";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(value) : "unsupported";
  }
  if (typeof value === "string") {
    return value;
  }
  return "unsupported";
}

export function cellKind(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "empty";
  }
  if (typeof value === "boolean") {
    return "boolean";
  }
  if (typeof value === "number") {
    return "number";
  }
  if (typeof value === "string") {
    return "text";
  }
  return "unsupported";
}

export function compareValues(left: unknown, right: unknown) {
  if (left === null || left === undefined) {
    return right === null || right === undefined ? 0 : 1;
  }
  if (right === null || right === undefined) {
    return -1;
  }
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  if (typeof left === "boolean" && typeof right === "boolean") {
    return Number(left) - Number(right);
  }
  return displayValue(left).localeCompare(displayValue(right), undefined, {
    numeric: true,
    sensitivity: "base"
  });
}
