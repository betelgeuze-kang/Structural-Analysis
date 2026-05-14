export function normalizeProvenanceValue(value){
  return String(value ?? '').trim();
}

export function basenameProvenanceLabel(value,fallback='--'){
  const token=normalizeProvenanceValue(value);
  if(!token)return fallback;
  const normalized=token.replace(/\\/g,'/');
  return normalized.split('/').filter(Boolean).pop()||fallback;
}

export function formatProvenanceTimestamp(value){
  const token=normalizeProvenanceValue(value);
  if(!token)return '--';
  const date=new Date(token);
  if(Number.isNaN(date.getTime()))return token;
  return date.toLocaleString();
}

export function buildViewerProvenanceModel({
  meta={},
  modelSourceMeta={},
  selection={},
  selectedCount=0,
  isolation={},
  clipLabel='--',
  drawingAssetLabel='--',
  reviewHref='',
}={}){
  const sourceLabel=normalizeProvenanceValue(meta.source_label||modelSourceMeta.label)||'--';
  const reportName=
    basenameProvenanceLabel(meta.source_path,'')
    || basenameProvenanceLabel(modelSourceMeta.resolvedPath,'')
    || normalizeProvenanceValue(meta.name)
    || '--';
  const timestampLabel=formatProvenanceTimestamp(meta.generated_at||meta.loaded_at||modelSourceMeta.loadedAt||'');
  const isolationLabel=isolation?.kind&&isolation?.value
    ?`${isolation.kind}=${isolation.label||isolation.value}`
    :'--';
  const normalizedClipLabel=normalizeProvenanceValue(clipLabel)||'--';
  const memberId=normalizeProvenanceValue(selection.memberId);
  const loadCase=normalizeProvenanceValue(selection.loadCase);
  const count=Number.isFinite(Number(selectedCount))?Number(selectedCount):0;
  return {
    sourceLabel,
    reportName,
    timestampLabel,
    selectionText:`member=${memberId||'--'} | drawing=${normalizeProvenanceValue(drawingAssetLabel)||'--'} | load_case=${loadCase||'--'} | selected=${count} | isolate=${isolationLabel} | clip=${normalizedClipLabel}`,
    reviewLink:{
      href:normalizeProvenanceValue(reviewHref),
      disabled:!normalizeProvenanceValue(reviewHref),
      text:normalizeProvenanceValue(reviewHref)?'Row provenance':'Row provenance unavailable',
    },
    stageLoadCase:{
      text:`Load case ${loadCase||'--'}`,
      accent:Boolean(loadCase),
    },
    stageSelection:{
      text:`Selection ${count} | ${memberId||'--'}`,
      warn:Boolean(memberId||count),
    },
    footerSelectionText:`${count} selected | load ${loadCase||'--'} | isolate ${isolationLabel} | clip ${normalizedClipLabel}`,
  };
}
