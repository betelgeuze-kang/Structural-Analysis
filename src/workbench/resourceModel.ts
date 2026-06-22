export type ResourceStatus = 'loading' | 'ready' | 'missing' | 'error'
export type JsonRecord = Record<string, unknown>

export type ResourceState = {
  status: ResourceStatus
  source: string
  data: JsonRecord | null
  error: string
}

export type ResourceMap = {
  authoring: ResourceState
  authoringSolver: ResourceState
  authoringOpsBundle: ResourceState
  authoringOpsBatch: ResourceState
  authoringOpsRegistry: ResourceState
  authoringPortfolio: ResourceState
  authoringServerOps: ResourceState
  authoringFamilyTrack: ResourceState
  authoringRuntimeSubmissionLane: ResourceState
  authoringRuntimeWritebackDepth: ResourceState
  authoringMultiProjectRuntimeWriteback: ResourceState
  authoringSolverFamilyBreadth: ResourceState
  authoringLocalRuntimeScenarioDepth: ResourceState
  authoringLocalVariantWritebackTrace: ResourceState
  authoringWritebackBreadth: ResourceState
  viewer: ResourceState
  drawing: ResourceState
  benchmark: ResourceState
  committeeSummary: ResourceState
  committeeReport: ResourceState
  developerPreview: ResourceState
  coreApiResult: ResourceState
  coreApiReport: ResourceState
  commercialWorkflowBreadth: ResourceState
  releaseGap: ResourceState
  registry: ResourceState
  registryIndex: ResourceState
  batch: ResourceState
}

export function createResource(status: ResourceStatus = 'loading'): ResourceState {
  return {
    status,
    source: '',
    data: null,
    error: '',
  }
}

export function createInitialResources(): ResourceMap {
  return {
    authoring: createResource(),
    authoringSolver: createResource(),
    authoringOpsBundle: createResource(),
    authoringOpsBatch: createResource(),
    authoringOpsRegistry: createResource(),
    authoringPortfolio: createResource(),
    authoringServerOps: createResource(),
    authoringFamilyTrack: createResource(),
    authoringRuntimeSubmissionLane: createResource(),
    authoringRuntimeWritebackDepth: createResource(),
    authoringMultiProjectRuntimeWriteback: createResource(),
    authoringSolverFamilyBreadth: createResource(),
    authoringLocalRuntimeScenarioDepth: createResource(),
    authoringLocalVariantWritebackTrace: createResource(),
    authoringWritebackBreadth: createResource(),
    viewer: createResource(),
    drawing: createResource(),
    benchmark: createResource(),
    committeeSummary: createResource(),
    committeeReport: createResource(),
    developerPreview: createResource(),
    coreApiResult: createResource(),
    coreApiReport: createResource(),
    commercialWorkflowBreadth: createResource(),
    releaseGap: createResource(),
    registry: createResource(),
    registryIndex: createResource(),
    batch: createResource(),
  }
}
