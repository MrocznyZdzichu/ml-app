const PIPELINE_DRAFT_PREFIX = "mlapp.pipeline-working-draft.";
const PIPELINE_DRAFT_STORAGE_VERSION = 1;

type PipelineWorkingDraftEnvelope = {
  storage_version: number;
  pipeline_id: string;
  pipeline_version_id: string;
  definition: unknown;
};

export function writePipelineWorkingDraft(
  pipelineId: string,
  pipelineVersionId: string,
  definition: unknown
) {
  try {
    const envelope: PipelineWorkingDraftEnvelope = {
      storage_version: PIPELINE_DRAFT_STORAGE_VERSION,
      pipeline_id: pipelineId,
      pipeline_version_id: pipelineVersionId,
      definition
    };
    window.sessionStorage.setItem(draftKey(pipelineId, pipelineVersionId), JSON.stringify(envelope));
  } catch {
    // The in-memory editor remains usable when browser storage is unavailable.
  }
}

export function readPipelineWorkingDraft(pipelineId: string, pipelineVersionId: string): unknown | null {
  try {
    const value = window.sessionStorage.getItem(draftKey(pipelineId, pipelineVersionId));
    if (!value) return null;
    const parsed = JSON.parse(value) as Partial<PipelineWorkingDraftEnvelope>;
    if (
      parsed.storage_version !== PIPELINE_DRAFT_STORAGE_VERSION
      || parsed.pipeline_id !== pipelineId
      || parsed.pipeline_version_id !== pipelineVersionId
      || !("definition" in parsed)
    ) {
      window.sessionStorage.removeItem(draftKey(pipelineId, pipelineVersionId));
      return null;
    }
    return parsed.definition;
  } catch {
    return null;
  }
}

export function clearPipelineWorkingDraft(pipelineId: string) {
  try {
    const prefix = `${PIPELINE_DRAFT_PREFIX}${pipelineId}.`;
    for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = window.sessionStorage.key(index);
      if (key?.startsWith(prefix)) window.sessionStorage.removeItem(key);
    }
    // Remove drafts written by the legacy pipeline-only cache contract.
    window.sessionStorage.removeItem(`${PIPELINE_DRAFT_PREFIX}${pipelineId}`);
  } catch {
    // Nothing else is required when browser storage is unavailable.
  }
}

function draftKey(pipelineId: string, pipelineVersionId: string) {
  return `${PIPELINE_DRAFT_PREFIX}${pipelineId}.${pipelineVersionId}`;
}
