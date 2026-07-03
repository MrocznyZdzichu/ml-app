const PIPELINE_DRAFT_PREFIX = "mlapp.pipeline-working-draft.";

export function writePipelineWorkingDraft(pipelineId: string, definition: unknown) {
  try {
    window.sessionStorage.setItem(draftKey(pipelineId), JSON.stringify(definition));
  } catch {
    // The in-memory editor remains usable when browser storage is unavailable.
  }
}

export function readPipelineWorkingDraft(pipelineId: string): unknown | null {
  try {
    const value = window.sessionStorage.getItem(draftKey(pipelineId));
    return value ? JSON.parse(value) : null;
  } catch {
    return null;
  }
}

export function clearPipelineWorkingDraft(pipelineId: string) {
  try {
    window.sessionStorage.removeItem(draftKey(pipelineId));
  } catch {
    // Nothing else is required when browser storage is unavailable.
  }
}

function draftKey(pipelineId: string) {
  return `${PIPELINE_DRAFT_PREFIX}${pipelineId}`;
}
