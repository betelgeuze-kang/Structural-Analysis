import {
  estimateStoryCount,
  extractModelPayload,
  normalizeElementType,
  rgbArrayToHex,
  safeNumber,
} from './viewer-model-normalizer.js';

const DEFAULT_NORMALIZATION_CHUNK_SIZE = 1200;

export const MATERIAL_FAMILY_ONTOLOGY = [
  {
    family: 'rigid_link',
    label: 'Rigid link',
    patterns: [/\brigid\b/i, /\brigid\s*bar\b/i, /rigidbar/i, /\bdummy\b/i, /\brlink\b/i, /\bmassless\b/i],
  },
  {
    family: 'prestressing',
    label: 'Prestressing tendon',
    patterns: [/\btendon\b/i, /\bstrand\b/i, /\bswpc\b/i, /\bpc\s*(bar|wire|strand)\b/i, /\bps\s*(bar|wire|strand)\b/i],
  },
  {
    family: 'rebar',
    label: 'Rebar',
    patterns: [/\brebar\b/i, /\breinforc/i, /\bksd\s*3504\b/i, /\bsd[3-7]\d{2}\b/i, /\bhd[0-9]+\b/i, /\bdb?[0-9]{2,}\b/i],
  },
  {
    family: 'cable',
    label: 'Cable',
    patterns: [/\bcable\b/i, /\bwire\s*rope\b/i, /\bstay\b/i, /\bsuspension\b/i],
  },
  {
    family: 'bolt_anchor',
    label: 'Bolt / anchor',
    patterns: [/\bbolt\b/i, /\banchor\b/i, /\bf10t\b/i, /\ba325\b/i, /\ba490\b/i, /\bstud\b/i, /\brock\s*bolt\b/i, /\bsegment\s*bolt\b/i],
  },
  {
    family: 'weld',
    label: 'Weld',
    patterns: [/\bweld\b/i, /\bfillet\b/i, /\bgroove\b/i],
  },
  {
    family: 'frp',
    label: 'FRP / composite retrofit',
    patterns: [/\bfrp\b/i, /\bcfrp\b/i, /\bgfrp\b/i, /\bcarbon\s*fiber\b/i, /\bglass\s*fiber\b/i],
  },
  {
    family: 'formwork_shoring',
    label: 'Formwork / shoring',
    patterns: [/\bform[-\s]*work\b/i, /\bfalse[-\s]*work\b/i, /\bshoring\b/i, /\btemporary\s*support\b/i],
  },
  {
    family: 'timber',
    label: 'Timber',
    patterns: [/\btimber\b/i, /\bwood\b/i, /\bglulam\b/i, /\bclt\b/i, /\blvl\b/i, /\bplywood\b/i],
  },
  {
    family: 'screed_topping',
    label: 'Screed / topping',
    patterns: [/\bscreed\b/i, /\btopping\b/i, /\bfloor\s*hardener\b/i, /\bself[-\s]*level(?:ing|ling)\b/i, /\blevel(?:ing|ling)\s*mortar\b/i],
  },
  {
    family: 'masonry',
    label: 'Masonry',
    patterns: [/\bmasonry\b/i, /\bbrick\b/i, /\bcmu\b/i, /\bblock\b/i, /\bmortar\b/i],
  },
  {
    family: 'ground_improvement',
    label: 'Ground improvement',
    patterns: [/\bground\s*improvement\b/i, /\bsoil[-\s]*cement\b/i, /\bjet\s*grout\b/i, /\bdcm\b/i, /\bdsm\b/i, /\bdeep\s*mix/i, /\bscp\b/i, /\bvibro[-\s]*(stone|replacement|compaction)\b/i],
  },
  {
    family: 'grout',
    label: 'Grout / backfill',
    patterns: [/\bgrout\b/i, /\bnon[-\s]*shrink\b/i, /\bbackfill\b/i, /\bcementitious\s*fill\b/i],
  },
  {
    family: 'waterproofing',
    label: 'Waterproofing / waterstop',
    patterns: [/\bwaterproof(?:ing)?\b/i, /\bwater[-\s]*stop\b/i, /\bbentonite\b/i, /\bsheet\s*membrane\b/i, /\bliquid\s*membrane\b/i, /\bpvc\s*membrane\b/i, /\btpo\b/i, /\bepdm\b/i],
  },
  {
    family: 'roofing',
    label: 'Roofing',
    patterns: [/\broof(?:ing)?\b/i, /\bshingle\b/i, /\broof\s*tile\b/i, /\broof\s*membrane\b/i],
  },
  {
    family: 'asphalt',
    label: 'Asphalt / bituminous',
    patterns: [/\basphalt\b/i, /\bbitumen\b/i, /\bbituminous\b/i, /\bpavement\b/i],
  },
  {
    family: 'insulation',
    label: 'Insulation',
    patterns: [/\binsulat/i, /\beps\b/i, /\bxps\b/i, /\bpolyurethane\s*foam\b/i, /\bpu\s*foam\b/i, /\bpir\b/i, /\bmineral\s*wool\b/i, /\brock\s*wool\b/i, /\bglass\s*wool\b/i],
  },
  {
    family: 'fireproofing',
    label: 'Fireproofing',
    patterns: [/\bfire[-\s]*proof/i, /\bfire[-\s]*stop/i, /\bintumescent\b/i, /\bsfrm\b/i, /\bsprayed\s*fire/i],
  },
  {
    family: 'coating',
    label: 'Coating / corrosion protection',
    patterns: [/\bcoating\b/i, /\bpaint\b/i, /\bprimer\b/i, /\bgalvani[sz](?:ed|ing)?\b/i, /\bzinc[-\s]*rich\b/i, /\banti[-\s]*corrosion\b/i],
  },
  {
    family: 'sealant_joint',
    label: 'Sealant / joint filler',
    patterns: [/\bsealant\b/i, /\bcaulk\b/i, /\bjoint\s*filler\b/i, /\bbacker\s*rod\b/i, /\bfiller\s*board\b/i],
  },
  {
    family: 'gypsum_board',
    label: 'Gypsum / board',
    patterns: [/\bgypsum\b/i, /\bdrywall\b/i, /\bplaster\s*board\b/i, /\bgwb\b/i, /\bcement\s*board\b/i, /\bfiber\s*cement\b/i],
  },
  {
    family: 'stone_tile',
    label: 'Stone / tile',
    patterns: [/\bstone\b/i, /\bmarble\b/i, /\btile\b/i, /\bterrazzo\b/i],
  },
  {
    family: 'aluminum',
    label: 'Aluminum',
    patterns: [/\balum/i, /\b6061\b/i, /\b6063\b/i, /\b5083\b/i],
  },
  {
    family: 'stainless_steel',
    label: 'Stainless steel',
    patterns: [/\bstainless\b/i, /\bsus\s*[0-9]+\b/i, /\bss\s*304\b/i, /\bss\s*316\b/i],
  },
  {
    family: 'cold_formed_steel',
    label: 'Cold formed steel',
    patterns: [/\bcold[-\s]*formed\b/i, /\bcfs\b/i, /\blgs\b/i, /\blight\s*gauge\b/i],
  },
  {
    family: 'metal_deck',
    label: 'Metal deck',
    patterns: [/\bdeck\b/i, /\bmetal\s*deck\b/i, /\bcomposite\s*deck\b/i],
  },
  {
    family: 'composite',
    label: 'Composite',
    patterns: [/\bsrc\b/i, /\bcft\b/i, /\bcomposite\b/i, /\bfilled\s*tube\b/i],
  },
  {
    family: 'facade_panel',
    label: 'Facade / cladding panel',
    patterns: [/\bcurtain\s*wall\b/i, /\bfacade\b/i, /\bcladding\b/i, /\baluminum\s*composite\s*panel\b/i, /\bacm\b/i, /\bacp\b/i, /\bgrc\b/i, /\bgfrc\b/i],
  },
  {
    family: 'sleeve_embed',
    label: 'Sleeve / embedded insert',
    patterns: [/\bpipe\s*sleeve\b/i, /\bsleeve\b/i, /\bcast[-\s]*in\s*insert\b/i, /\bembed(?:ded)?\s*insert\b/i, /\bhanger\s*insert\b/i],
  },
  {
    family: 'rail_fastener',
    label: 'Rail fastener',
    patterns: [/\bfastener\b/i, /\bpandrol\b/i, /\bclip\b/i, /\btoe\s*load\b/i],
  },
  {
    family: 'rail_sleeper',
    label: 'Rail sleeper / tie',
    patterns: [/\bsleeper\b/i, /\brail\s*tie\b/i, /\bconcrete\s*tie\b/i, /\btimber\s*tie\b/i],
  },
  {
    family: 'rail_steel',
    label: 'Rail steel',
    patterns: [/\brail\b/i, /\buic\s*60\b/i, /\bkrs[-_\s]*rail\b/i],
  },
  {
    family: 'steel',
    label: 'Structural steel',
    patterns: [/\bsteel\b/i, /\bsm\s*[0-9]+\b/i, /\bsm[0-9]+\b/i, /\bss\s*[0-9]+\b/i, /\bss[0-9]+\b/i, /\bsn\s*[0-9]+\b/i, /\bsn[0-9]+\b/i, /\bq[0-9]{3}\b/i, /\bhrb[0-9]+\b/i, /\ba36\b/i, /\ba572\b/i, /\ba992\b/i],
  },
  {
    family: 'concrete',
    label: 'Concrete',
    patterns: [/\bconcrete\b/i, /\bconc\b/i, /\buhpc\b/i, /\bhpc\b/i, /\blwac\b/i, /\bshotcrete\b/i, /\bprecast\b/i, /\bsegment\s*concrete\b/i, /\bc[0-9]{2,}\b/i, /\bfck\s*[0-9]+\b/i],
  },
  {
    family: 'seismic_isolator',
    label: 'Seismic isolator',
    patterns: [/\bisolat/i, /\bfriction\s*pendulum\b/i, /\bfps\b/i, /\blead\s*rubber\b/i, /\blrb\b/i],
  },
  {
    family: 'elastomeric_bearing',
    label: 'Elastomeric bearing',
    patterns: [/\belastomer/i, /\brubber\s*bearing\b/i, /\bptfe\s*bearing\b/i, /\bneoprene\b/i],
  },
  {
    family: 'pot_spherical_bearing',
    label: 'Pot / spherical bearing',
    patterns: [/\bpot\s*bearing\b/i, /\bspherical\s*bearing\b/i, /\bdisk\s*bearing\b/i, /\bdisc\s*bearing\b/i],
  },
  {
    family: 'resilient_pad',
    label: 'Resilient pad',
    patterns: [/\bresilient\s*pad\b/i, /\bpad\b/i, /\beva\b/i, /\bunder[-\s]*sleeper\b/i],
  },
  {
    family: 'expansion_joint',
    label: 'Expansion joint',
    patterns: [/\bexpansion\s*joint\b/i, /\bmodular\s*joint\b/i, /\bfinger\s*joint\b/i, /\bbridge\s*joint\b/i],
  },
  {
    family: 'damper',
    label: 'Damper / energy device',
    patterns: [/\bdamper\b/i, /\bviscous\b/i, /\bviscoelastic\b/i, /\btmd\b/i, /\btuned\s*mass\b/i],
  },
  {
    family: 'spring_link',
    label: 'Spring / nonlinear link',
    patterns: [/\bspring\b/i, /\bgap\b/i, /\buplift\b/i, /\bcompression[-\s]*only\b/i, /\bp[-\s]*y\b/i, /\bq[-\s]*z\b/i, /\bt[-\s]*z\b/i],
  },
  {
    family: 'mass',
    label: 'Mass / inertia',
    patterns: [/\blumped\s*mass\b/i, /\binertia\b/i, /\bmass\b/i],
  },
  {
    family: 'glass',
    label: 'Glass',
    patterns: [/\bglass\b/i, /\bglazing\b/i],
  },
  {
    family: 'ballast',
    label: 'Ballast',
    patterns: [/\bballast\b/i, /\bgranite\s*ballast\b/i],
  },
  {
    family: 'soil',
    label: 'Soil / geotechnical',
    patterns: [/\bsoil\b/i, /\bclay\b/i, /\bsand\b/i, /\bgravel\b/i, /\brock\b/i],
  },
  {
    family: 'geosynthetic',
    label: 'Geosynthetic / membrane',
    patterns: [/\bgeotextile\b/i, /\bgeomembrane\b/i, /\bgeogrid\b/i, /\bhdpe\s*membrane\b/i, /\bwaterproof(?:ing)?\s*membrane\b/i],
  },
  {
    family: 'adhesive_resin',
    label: 'Adhesive / resin',
    patterns: [/\badhesive\b/i, /\bepoxy\b/i, /\bresin\b/i, /\bbonding\s*agent\b/i, /\binjection\s*resin\b/i, /\bchemical\s*anchor\b/i],
  },
];

const MATERIAL_FAMILY_LABEL_BY_ID = new Map(MATERIAL_FAMILY_ONTOLOGY.map(row => [row.family, row.label]));

export const SECTION_DESCRIPTOR_ONTOLOGY = [
  { family: 'wall', shape: 'retaining_wall', patterns: [/\bretaining\s*wall\b/i, /\bbasement\s*wall\b/i] },
  { family: 'wall', shape: 'diaphragm_wall', patterns: [/\bd[-_\s]*wall\b/i, /\bdiaphragm\s*wall\b/i, /\bslurry\s*wall\b/i] },
  { family: 'wall', shape: 'parapet', patterns: [/\bparapet\b/i] },
  { family: 'wall', shape: 'wall', patterns: [/\bwall\b/i, /\bshear\s*wall\b/i, /\bcore\b/i] },
  { family: 'foundation', shape: 'pile', patterns: [/\bpile\b/i, /\bpile\s*cap\b/i, /\bcaisson\b/i, /\bdrilled\s*shaft\b/i] },
  { family: 'foundation', shape: 'pier', patterns: [/\bpier\b/i, /\bpedestal\b/i] },
  { family: 'foundation', shape: 'grade_beam', patterns: [/\bgrade\s*beam\b/i, /\btie\s*beam\b/i] },
  { family: 'foundation', shape: 'mat_foundation', patterns: [/\bmat\s*foundation\b/i, /\braft\b/i, /\braft\s*foundation\b/i] },
  { family: 'foundation', shape: 'footing', patterns: [/\bfooting\b/i, /\bspread\s*footing\b/i, /\bfoundation\b/i] },
  { family: 'connection', shape: 'base_plate', patterns: [/\bbase\s*plate\b/i] },
  { family: 'connection', shape: 'gusset_plate', patterns: [/\bgusset\b/i] },
  { family: 'connection', shape: 'splice_plate', patterns: [/\bsplice\b/i] },
  { family: 'connection', shape: 'embed_plate', patterns: [/\bembed(?:ded)?\s*plate\b/i, /\banchor\s*plate\b/i] },
  { family: 'slab', shape: 'stair', patterns: [/\bstair\b/i, /\bstaircase\b/i, /\blanding\b/i] },
  { family: 'slab', shape: 'ramp', patterns: [/\bramp\b/i] },
  { family: 'slab', shape: 'balcony', patterns: [/\bbalcony\b/i, /\bcantilever\s*slab\b/i] },
  { family: 'slab', shape: 'roof_slab', patterns: [/\broof\s*slab\b/i, /\bpodium\s*slab\b/i] },
  { family: 'slab', shape: 'slab', patterns: [/\bslab\b/i, /\bplate\b/i, /\bdeck\b/i, /\bmat\b/i] },
  { family: 'column', shape: 'mega_column', patterns: [/\bmega\s*column\b/i, /\bsuper\s*column\b/i] },
  { family: 'column', shape: 'column', patterns: [/\bcolumn\b/i, /\bcol\b/i] },
  { family: 'column', shape: 'wall_boundary', patterns: [/\bboundary\s*column\b/i, /\bwall\s*boundary\b/i] },
  { family: 'beam', shape: 'spandrel_beam', patterns: [/\bspandrel\b/i] },
  { family: 'beam', shape: 'lintel', patterns: [/\blintel\b/i] },
  { family: 'beam', shape: 'joist', patterns: [/\bjoist\b/i] },
  { family: 'beam', shape: 'rafter', patterns: [/\brafter\b/i] },
  { family: 'beam', shape: 'purlin_girt', patterns: [/\bpurlin\b/i, /\bgirt\b/i] },
  { family: 'beam', shape: 'edge_beam', patterns: [/\bedge\s*beam\b/i, /\bperimeter\s*beam\b/i] },
  { family: 'beam', shape: 'beam', patterns: [/\bbeam\b/i, /\bgirder\b/i] },
  { family: 'beam', shape: 'coupling_beam', patterns: [/\bcoupling\s*beam\b/i] },
  { family: 'beam', shape: 'transfer_girder', patterns: [/\btransfer\s*(girder|beam)\b/i] },
  { family: 'brace', shape: 'buckling_restrained_brace', patterns: [/\bbrb\b/i, /\bbuckling[-\s]*restrained\b/i] },
  { family: 'brace', shape: 'brace', patterns: [/\bbrace\b/i, /\bbracing\b/i] },
  { family: 'outrigger', shape: 'outrigger', patterns: [/\boutrigger\b/i, /\bbelt\s*truss\b/i, /\bbelt\s*wall\b/i] },
  { family: 'truss', shape: 'truss', patterns: [/\btruss\b/i, /\bspace\s*frame\b/i] },
  { family: 'diaphragm', shape: 'diaphragm', patterns: [/\bdiaphragm\b/i, /\bcollector\b/i, /\bdrag\s*strut\b/i] },
  { family: 'strut_tie', shape: 'strut_tie', patterns: [/\bstrut\b/i, /\btie\b/i, /\btie[-\s]*rod\b/i, /\btieback\b/i, /\bground\s*anchor\b/i] },
  { family: 'connection', shape: 'base_plate', patterns: [/\bbase\s*plate\b/i] },
  { family: 'connection', shape: 'gusset_plate', patterns: [/\bgusset\b/i] },
  { family: 'connection', shape: 'splice_plate', patterns: [/\bsplice\b/i] },
  { family: 'connection', shape: 'embed_plate', patterns: [/\bembed(?:ded)?\s*plate\b/i, /\banchor\s*plate\b/i] },
  { family: 'cable', shape: 'cable', patterns: [/\bcable\b/i, /\btendon\b/i, /\bstrand\b/i] },
  { family: 'link_device', shape: 'damper', patterns: [/\bdamper\b/i, /\bviscous\b/i, /\bviscoelastic\b/i, /\btmd\b/i] },
  { family: 'link_device', shape: 'isolator', patterns: [/\bisolat/i, /\bfriction\s*pendulum\b/i, /\bfps\b/i, /\blead\s*rubber\b/i, /\blrb\b/i] },
  { family: 'link_device', shape: 'spring_link', patterns: [/\bspring\b/i, /\bgap\b/i, /\buplift\b/i, /\bcompression[-\s]*only\b/i, /\bp[-\s]*y\b/i, /\bq[-\s]*z\b/i, /\bt[-\s]*z\b/i] },
  { family: 'rail', shape: 'rail', patterns: [/\brail\b/i, /\buic\s*60\b/i] },
  { family: 'tunnel', shape: 'segment_lining', patterns: [/\btunnel\b/i, /\bsegment\b/i, /\blining\b/i] },
  { family: 'steel', shape: 'h_beam', patterns: [/^h[-_ ]?[0-9]/i, /\bh[-_ ][0-9]/i, /\bi[-_ ]?[0-9]/i, /\bwf[-_ ]?[0-9]/i] },
  { family: 'steel', shape: 'box', patterns: [/\bbox\b/i, /\bpipe\b/i, /\btube\b/i, /\bchs\b/i, /\bshs\b/i, /\brhs\b/i] },
  { family: 'steel', shape: 'angle_channel', patterns: [/\bangle\b/i, /\bchannel\b/i, /^l[-_ ]?[0-9]/i, /^c[-_ ]?[0-9]/i] },
  { family: 'concrete', shape: 'rect', patterns: [/\brect\b/i, /\brectangle\b/i, /\brc\b/i, /\bconc\b/i] },
  { family: 'composite', shape: 'composite', patterns: [/\bsrc\b/i, /\bcft\b/i, /\bcomposite\b/i] },
];

function normalizeSelectionValue(value) {
  const text = String(value ?? '').trim();
  return text || '';
}

function buildReviewRowIsolationToken(data) {
  return [
    normalizeSelectionValue(data?.review_case_id) || '--',
    normalizeSelectionValue(data?.review_row_label) || '--',
    normalizeSelectionValue(data?.member_id) || '--',
    normalizeSelectionValue(data?.target_element_id ?? data?.id) || '--',
  ].join('::');
}

export function buildSectionFamilySummary(sectionUsageRows) {
  const summaryByFamily = new Map();
  (Array.isArray(sectionUsageRows) ? sectionUsageRows : []).forEach(row => {
    const family = normalizeSelectionValue(row?.inferred_family) || 'unclassified';
    const shape = normalizeSelectionValue(row?.inferred_shape) || '--';
    const next = summaryByFamily.get(family) || {
      family,
      shapeMix: new Set(),
      sectionCount: 0,
      usageCount: 0,
      representativeSectionName: '',
    };
    next.sectionCount += 1;
    next.usageCount += safeNumber(row?.usage_count, 0);
    if (shape && shape !== '--') next.shapeMix.add(shape);
    if (!next.representativeSectionName) {
      next.representativeSectionName = normalizeSelectionValue(row?.name || row?.section_name || row?.display_label || row?.section_id);
    }
    summaryByFamily.set(family, next);
  });
  return [...summaryByFamily.values()]
    .map(row => ({
      family: row.family,
      section_count: row.sectionCount,
      usage_count: row.usageCount,
      shape_mix_label: [...row.shapeMix].sort().join(', ') || '--',
      representative_section_name: row.representativeSectionName || '--',
    }))
    .sort((a, b) => b.usage_count - a.usage_count || b.section_count - a.section_count || a.family.localeCompare(b.family))
    .slice(0, 12);
}

export function buildGroupSummary(groupRows) {
  return (Array.isArray(groupRows) ? groupRows : [])
    .map(row => ({
      group_name: normalizeSelectionValue(row?.name) || '--',
      element_count: safeNumber(row?.element_count, 0),
      node_count: safeNumber(row?.node_count, 0),
      physical_line_span: safeNumber(row?.physical_line_span, 0),
      representative_element_id: Array.isArray(row?.element_ids_head) && row.element_ids_head.length ? row.element_ids_head[0] : null,
    }))
    .sort((a, b) => b.element_count - a.element_count || b.node_count - a.node_count || a.group_name.localeCompare(b.group_name))
    .slice(0, 12);
}

function buildMaterialDescriptorIndex(materialRows, metadata = {}) {
  const colorById = new Map(
    (Array.isArray(metadata?.material_colors) ? metadata.material_colors : [])
      .map(row => [normalizeSelectionValue(row?.material_id), rgbArrayToHex(row?.fill_rgb || row?.wire_rgb)])
      .filter(([materialId, color]) => Boolean(materialId && color))
  );
  const descriptorsById = new Map();
  (Array.isArray(materialRows) ? materialRows : []).forEach(row => {
    const materialId = normalizeSelectionValue(row?.id ?? row?.material_id);
    if (!materialId) return;
    const rawTokens = (Array.isArray(row?.raw_tokens) ? row.raw_tokens : [])
      .map(value => normalizeSelectionValue(value))
      .filter(Boolean);
    const materialName = normalizeSelectionValue(row?.name || row?.material_name) || `Material ${materialId}`;
    const materialGrade = normalizeSelectionValue(row?.grade || row?.material_grade || rawTokens[0]) || '--';
    const classification = classifyMaterialFamily({
      ...row,
      material_name: materialName,
      material_grade: materialGrade,
      raw_tokens: rawTokens,
    });
    descriptorsById.set(materialId, {
      material_id: materialId,
      material_name: materialName,
      material_grade: materialGrade,
      material_label: materialGrade === '--' ? materialName : `${materialName} ${materialGrade}`,
      material_family: classification.family,
      material_family_label: classification.label,
      material_family_source: classification.source,
      color: colorById.get(materialId) || '',
    });
  });
  return descriptorsById;
}

function buildSectionMaterialUsageIndex(elementRows, materialRows, metadata = {}) {
  const materialDescriptorById = buildMaterialDescriptorIndex(materialRows, metadata);
  const usageBySectionId = new Map();
  (Array.isArray(elementRows) ? elementRows : []).forEach(element => {
    const sectionId = normalizeSelectionValue(element?.section_id ?? element?.sectionId ?? element?.section);
    const materialId = normalizeSelectionValue(element?.material_id ?? element?.materialId ?? element?.material);
    if (!sectionId || !materialId) return;
    const sectionEntry = usageBySectionId.get(sectionId) || new Map();
    const descriptor = materialDescriptorById.get(materialId) || {};
    const materialEntry = sectionEntry.get(materialId) || {
      material_id: materialId,
      material_label: normalizeSelectionValue(
        element?.material_label || descriptor.material_label || descriptor.material_name || materialId
      ) || materialId,
      material_family: normalizeSelectionValue(element?.material_family || descriptor.material_family) || '--',
      material_family_label: normalizeSelectionValue(element?.material_family_label || descriptor.material_family_label) || '--',
      material_color: normalizeSelectionValue(element?.material_color || descriptor.color),
      usage_count: 0,
      member_sample_id: normalizeSelectionValue(element?.member_id),
      element_sample_id: normalizeSelectionValue(element?.id),
      element_family_mix: {},
    };
    const elementFamily = normalizeElementType(element?.family || element?.type);
    materialEntry.usage_count += 1;
    materialEntry.element_family_mix[elementFamily] = safeNumber(materialEntry.element_family_mix[elementFamily], 0) + 1;
    if (!materialEntry.member_sample_id) materialEntry.member_sample_id = normalizeSelectionValue(element?.member_id);
    if (!materialEntry.element_sample_id) materialEntry.element_sample_id = normalizeSelectionValue(element?.id);
    sectionEntry.set(materialId, materialEntry);
    usageBySectionId.set(sectionId, sectionEntry);
  });
  return usageBySectionId;
}

function buildSectionMaterialUsageSummary(materialUsageById) {
  return [...(materialUsageById instanceof Map ? materialUsageById.values() : [])]
    .map(row => ({
      material_id: normalizeSelectionValue(row?.material_id),
      material_label: normalizeSelectionValue(row?.material_label || row?.material_id) || '--',
      material_family: normalizeSelectionValue(row?.material_family) || '--',
      material_family_label: normalizeSelectionValue(row?.material_family_label) || '--',
      material_color: normalizeSelectionValue(row?.material_color),
      usage_count: safeNumber(row?.usage_count, 0),
      member_sample_id: normalizeSelectionValue(row?.member_sample_id),
      element_sample_id: normalizeSelectionValue(row?.element_sample_id),
      element_family_mix: row?.element_family_mix && typeof row.element_family_mix === 'object'
        ? { ...row.element_family_mix }
        : {},
      element_family_mix_label: buildElementFamilyMixLabel(row?.element_family_mix || {}),
    }))
    .filter(row => row.material_id)
    .sort((a, b) => b.usage_count - a.usage_count || a.material_label.localeCompare(b.material_label) || a.material_id.localeCompare(b.material_id))
    .slice(0, 8);
}

export function buildSectionCatalogSummary(sectionRows, sectionUsageRows, elementRows = [], materialRows = [], metadata = {}) {
  const usageById = new Map(
    (Array.isArray(sectionUsageRows) ? sectionUsageRows : [])
      .map(row => [normalizeSelectionValue(row?.section_id), row])
      .filter(([sectionId]) => Boolean(sectionId))
  );
  const materialUsageBySectionId = buildSectionMaterialUsageIndex(elementRows, materialRows, metadata);
  return (Array.isArray(sectionRows) ? sectionRows : [])
    .map(row => {
      const sectionId = normalizeSelectionValue(row?.id);
      if (!sectionId) return null;
      const rawTokens = (Array.isArray(row?.raw_tokens) ? row.raw_tokens : [])
        .map(value => normalizeSelectionValue(value))
        .filter(Boolean);
      const usageRow = usageById.get(sectionId) || {};
      const fallbackDescriptor = inferSectionDescriptor({
        ...row,
        ...usageRow,
        section_id: sectionId,
        raw_tokens: rawTokens,
      });
      const inferredFamily = normalizeSelectionValue(usageRow?.inferred_family) || fallbackDescriptor.section_family;
      const inferredShape = normalizeSelectionValue(usageRow?.inferred_shape) || fallbackDescriptor.section_shape;
      return {
        section_id: sectionId,
        section_name: normalizeSelectionValue(row?.section_name || row?.label || row?.name),
        display_label: normalizeSelectionValue(rawTokens[0] || row?.section_name || row?.label || row?.name || sectionId),
        raw_tokens_head: rawTokens.slice(0, 4),
        inferred_family: inferredFamily,
        inferred_shape: inferredShape,
        section_descriptor_source: normalizeSelectionValue(usageRow?.inferred_family) ? 'section_library' : fallbackDescriptor.source,
        usage_count: safeNumber(
          usageRow?.usage_count,
          [...(materialUsageBySectionId.get(sectionId)?.values() || [])].reduce((sum, materialRow) => sum + safeNumber(materialRow?.usage_count, 0), 0)
        ),
        material_usage_summary: buildSectionMaterialUsageSummary(materialUsageBySectionId.get(sectionId)),
      };
    })
    .filter(Boolean)
    .sort((a, b) => b.usage_count - a.usage_count || a.display_label.localeCompare(b.display_label) || a.section_id.localeCompare(b.section_id));
}

function buildMaterialClassificationText(row = {}) {
  const rawTokens = Array.isArray(row?.raw_tokens)
    ? row.raw_tokens.map(value => normalizeSelectionValue(value)).filter(Boolean)
    : [];
  return [
    row?.name,
    row?.material_name,
    row?.grade,
    row?.material_grade,
    row?.material_label,
    row?.type,
    row?.material_type,
    row?.code,
    ...rawTokens,
  ].map(value => normalizeSelectionValue(value)).filter(Boolean).join(' ');
}

export function classifyMaterialFamily(row = {}) {
  const text = buildMaterialClassificationText(row);
  const matched = MATERIAL_FAMILY_ONTOLOGY.find(definition => definition.patterns.some(pattern => pattern.test(text)));
  if (!matched) {
    return {
      family: 'unclassified',
      label: 'Unclassified',
      source: 'unclassified',
      token: '',
    };
  }
  return {
    family: matched.family,
    label: matched.label,
    source: 'ontology',
    token: text,
  };
}

function inferMaterialFamily(row = {}) {
  return classifyMaterialFamily(row).family;
}

function knownMaterialFamily(value) {
  const family = normalizeSelectionValue(value);
  return family && family !== '--' && family !== 'unclassified' ? family : '';
}

export function inferSectionDescriptor(row = {}) {
  const rawTokens = Array.isArray(row?.raw_tokens)
    ? row.raw_tokens.map(value => normalizeSelectionValue(value)).filter(Boolean)
    : [];
  const text = [
    row?.section_id,
    row?.id,
    row?.name,
    row?.section_name,
    row?.display_label,
    row?.label,
    row?.inferred_family,
    row?.inferred_shape,
    ...rawTokens,
  ].map(value => normalizeSelectionValue(value)).filter(Boolean).join(' ');
  const matched = SECTION_DESCRIPTOR_ONTOLOGY.find(definition => definition.patterns.some(pattern => pattern.test(text)));
  if (!matched) {
    return {
      section_family: 'unclassified',
      section_shape: '--',
      source: 'unclassified',
    };
  }
  return {
    section_family: matched.family,
    section_shape: matched.shape,
    source: 'ontology',
  };
}

export function buildMaterialFamilyCoverageSummary(materialRows = []) {
  const rowsByFamily = new Map();
  (Array.isArray(materialRows) ? materialRows : []).forEach(row => {
    const family = normalizeSelectionValue(row?.material_family) || 'unclassified';
    const current = rowsByFamily.get(family) || {
      family,
      label: normalizeSelectionValue(row?.material_family_label) || MATERIAL_FAMILY_LABEL_BY_ID.get(family) || family,
      material_count: 0,
      used_material_count: 0,
      usage_count: 0,
      missing_definition_count: 0,
      unclassified_count: 0,
      sample_material_label: '',
    };
    current.material_count += 1;
    if (safeNumber(row?.usage_count, 0) > 0) current.used_material_count += 1;
    current.usage_count += safeNumber(row?.usage_count, 0);
    if (normalizeSelectionValue(row?.source_status) === 'missing_material_definition') current.missing_definition_count += 1;
    if (family === 'unclassified') current.unclassified_count += 1;
    if (!current.sample_material_label) current.sample_material_label = normalizeSelectionValue(row?.material_label || row?.material_name || row?.material_id);
    rowsByFamily.set(family, current);
  });
  const rows = [...rowsByFamily.values()]
    .sort((a, b) => b.usage_count - a.usage_count || b.material_count - a.material_count || a.family.localeCompare(b.family));
  const materialCount = rows.reduce((sum, row) => sum + safeNumber(row.material_count, 0), 0);
  const unclassifiedMaterialCount = rows.reduce((sum, row) => sum + safeNumber(row.unclassified_count, 0), 0);
  const missingDefinitionCount = rows.reduce((sum, row) => sum + safeNumber(row.missing_definition_count, 0), 0);
  return {
    schema_version: 'structure-viewer-material-family-coverage.v1',
    status: materialCount && !unclassifiedMaterialCount && !missingDefinitionCount ? 'ready' : materialCount ? 'needs_review' : 'missing',
    ontology_family_count: MATERIAL_FAMILY_ONTOLOGY.length,
    family_count: rows.length,
    known_family_count: rows.filter(row => row.family !== 'unclassified').length,
    material_count: materialCount,
    unclassified_material_count: unclassifiedMaterialCount,
    missing_definition_count: missingDefinitionCount,
    rows,
  };
}

function buildElementFamilyMixLabel(familyCounts = {}) {
  return Object.entries(familyCounts)
    .filter(([, count]) => safeNumber(count, 0) > 0)
    .sort((a, b) => safeNumber(b[1], 0) - safeNumber(a[1], 0) || a[0].localeCompare(b[0]))
    .map(([family, count]) => `${family}:${safeNumber(count, 0)}`)
    .join(', ') || '--';
}

function buildSectionDescriptorIndex(metadata = {}) {
  const descriptorsById = new Map();
  const mergeDescriptor = (sectionId, patch = {}) => {
    const normalizedId = normalizeSelectionValue(sectionId);
    if (!normalizedId) return;
    const current = descriptorsById.get(normalizedId) || { section_id: normalizedId };
    const next = { ...current };
    Object.entries(patch)
      .map(([key, value]) => [key, normalizeSelectionValue(value)])
      .filter(([, value]) => Boolean(value))
      .forEach(([key, value]) => {
        if (
          (key === 'section_family' || key === 'section_shape')
          && normalizeSelectionValue(next[key])
          && (value === 'unclassified' || value === '--')
        ) {
          return;
        }
        next[key] = value;
      });
    descriptorsById.set(normalizedId, next);
  };
  const sectionLibrary = metadata?.section_library && typeof metadata.section_library === 'object'
    ? metadata.section_library
    : {};
  const usageRows = Array.isArray(sectionLibrary.usage_summary) ? sectionLibrary.usage_summary : [];
  usageRows.forEach(row => {
    const sectionId = normalizeSelectionValue(row?.section_id);
    mergeDescriptor(sectionId, {
      section_label: row?.name || row?.section_name || sectionId,
      section_name: row?.name || row?.section_name || sectionId,
      section_family: row?.inferred_family,
      section_shape: row?.inferred_shape,
    });
  });
  const sectionRows = Array.isArray(metadata?.section_rows)
    ? metadata.section_rows
    : Array.isArray(metadata?.sections)
      ? metadata.sections
      : [];
  sectionRows.forEach(row => {
    const sectionId = normalizeSelectionValue(row?.id ?? row?.section_id);
    const rawTokens = Array.isArray(row?.raw_tokens)
      ? row.raw_tokens.map(value => normalizeSelectionValue(value)).filter(Boolean)
      : [];
    const fallbackDescriptor = inferSectionDescriptor({
      ...row,
      section_id: sectionId,
      raw_tokens: rawTokens,
    });
    mergeDescriptor(sectionId, {
      section_label: rawTokens[0] || row?.section_name || row?.label || row?.name || sectionId,
      section_name: row?.section_name || row?.label || row?.name || rawTokens[0] || sectionId,
      section_family: fallbackDescriptor.section_family,
      section_shape: fallbackDescriptor.section_shape,
    });
  });
  return descriptorsById;
}

function buildMaterialSectionUsageSummary(sectionUsageById) {
  return [...(sectionUsageById instanceof Map ? sectionUsageById.values() : [])]
    .map(row => ({
      section_id: normalizeSelectionValue(row?.section_id),
      section_label: normalizeSelectionValue(row?.section_label || row?.section_name || row?.section_id) || '--',
      section_family: normalizeSelectionValue(row?.section_family) || '--',
      section_shape: normalizeSelectionValue(row?.section_shape) || '--',
      usage_count: safeNumber(row?.usage_count, 0),
      member_sample_id: normalizeSelectionValue(row?.member_sample_id),
      element_sample_id: normalizeSelectionValue(row?.element_sample_id),
      element_family_mix: row?.element_family_mix && typeof row.element_family_mix === 'object'
        ? { ...row.element_family_mix }
        : {},
      element_family_mix_label: buildElementFamilyMixLabel(row?.element_family_mix || {}),
    }))
    .filter(row => row.section_id)
    .sort((a, b) => b.usage_count - a.usage_count || a.section_label.localeCompare(b.section_label) || a.section_id.localeCompare(b.section_id))
    .slice(0, 12);
}

function buildMaterialUsageIndex(elementRows, metadata = {}) {
  const sectionDescriptorById = buildSectionDescriptorIndex(metadata);
  const usageById = new Map();
  (Array.isArray(elementRows) ? elementRows : []).forEach(element => {
    const materialId = normalizeSelectionValue(element?.material_id ?? element?.materialId ?? element?.material);
    if (!materialId) return;
    const entry = usageById.get(materialId) || {
      material_id: materialId,
      usage_count: 0,
      element_family_mix: {},
      section_usage_by_id: new Map(),
    };
    const elementFamily = normalizeElementType(element?.family || element?.type);
    entry.usage_count += 1;
    entry.element_family_mix[elementFamily] = safeNumber(entry.element_family_mix[elementFamily], 0) + 1;
    const sectionId = normalizeSelectionValue(element?.section_id ?? element?.sectionId ?? element?.section);
    if (sectionId) {
      const descriptor = sectionDescriptorById.get(sectionId) || {};
      const sectionEntry = entry.section_usage_by_id.get(sectionId) || {
        section_id: sectionId,
        section_label: normalizeSelectionValue(element?.section || descriptor.section_label || descriptor.section_name || sectionId) || sectionId,
        section_family: normalizeSelectionValue(element?.section_family || descriptor.section_family) || '--',
        section_shape: normalizeSelectionValue(element?.section_shape || descriptor.section_shape) || '--',
        usage_count: 0,
        member_sample_id: normalizeSelectionValue(element?.member_id),
        element_sample_id: normalizeSelectionValue(element?.id),
        element_family_mix: {},
      };
      sectionEntry.usage_count += 1;
      sectionEntry.element_family_mix[elementFamily] = safeNumber(sectionEntry.element_family_mix[elementFamily], 0) + 1;
      if (!sectionEntry.member_sample_id) sectionEntry.member_sample_id = normalizeSelectionValue(element?.member_id);
      if (!sectionEntry.element_sample_id) sectionEntry.element_sample_id = normalizeSelectionValue(element?.id);
      entry.section_usage_by_id.set(sectionId, sectionEntry);
    }
    usageById.set(materialId, entry);
  });
  return usageById;
}

export function buildMaterialCatalogSummary(materialRows, elementRows, metadata = {}) {
  const usageById = buildMaterialUsageIndex(elementRows, metadata);
  const colorById = new Map(
    (Array.isArray(metadata?.material_colors) ? metadata.material_colors : [])
      .map(row => [normalizeSelectionValue(row?.material_id), rgbArrayToHex(row?.fill_rgb || row?.wire_rgb)])
      .filter(([materialId, color]) => Boolean(materialId && color))
  );
  const rowsById = new Map();
  (Array.isArray(materialRows) ? materialRows : []).forEach(row => {
    const materialId = normalizeSelectionValue(row?.id ?? row?.material_id);
    if (!materialId) return;
    rowsById.set(materialId, row);
  });
  const materialIds = new Set([...rowsById.keys(), ...usageById.keys()]);
  return [...materialIds].map(materialId => {
    const row = rowsById.get(materialId) || {};
    const usageRow = usageById.get(materialId) || {};
    const rawTokens = (Array.isArray(row?.raw_tokens) ? row.raw_tokens : [])
      .map(value => normalizeSelectionValue(value))
      .filter(Boolean);
    const materialName = normalizeSelectionValue(row?.name || row?.material_name) || `Material ${materialId}`;
    const materialGrade = normalizeSelectionValue(row?.grade || row?.material_grade || rawTokens[0]) || '--';
    const materialFamilyClassification = classifyMaterialFamily({
      ...row,
      material_name: materialName,
      material_grade: materialGrade,
      raw_tokens: rawTokens,
    });
    const materialFamily = materialFamilyClassification.family;
    const sourceStatus = rowsById.has(materialId) ? 'source_material' : 'missing_material_definition';
    const usageCount = safeNumber(usageRow?.usage_count, 0);
    const elementFamilyMix = usageRow?.element_family_mix && typeof usageRow.element_family_mix === 'object'
      ? { ...usageRow.element_family_mix }
      : {};
    const sectionUsageSummary = buildMaterialSectionUsageSummary(usageRow?.section_usage_by_id);
    return {
      material_id: materialId,
      material_name: materialName,
      material_grade: materialGrade,
      material_label: materialGrade === '--' ? materialName : `${materialName} ${materialGrade}`,
      material_family: materialFamily,
      material_family_label: materialFamilyClassification.label,
      material_family_source: materialFamilyClassification.source,
      material_family_token: materialFamilyClassification.token,
      material_family_known: materialFamily !== 'unclassified',
      usage_count: usageCount,
      element_family_mix: elementFamilyMix,
      element_family_mix_label: buildElementFamilyMixLabel(elementFamilyMix),
      section_usage_summary: sectionUsageSummary,
      elastic_modulus: safeNumber(row?.elastic_modulus ?? row?.e_modulus ?? rawTokens[7], 0),
      poisson_ratio: safeNumber(row?.poisson_ratio ?? row?.poisson ?? rawTokens[8], 0),
      thermal_coefficient: safeNumber(row?.thermal_coefficient ?? rawTokens[9], 0),
      density: safeNumber(row?.density ?? rawTokens[10], 0),
      source_status: sourceStatus,
      color: colorById.get(materialId) || '',
      raw_tokens_head: rawTokens.slice(0, 8),
    };
  })
    .sort((a, b) => b.usage_count - a.usage_count || a.material_family.localeCompare(b.material_family) || a.material_id.localeCompare(b.material_id));
}

export function buildThicknessCatalogSummary(thicknessRows) {
  return (Array.isArray(thicknessRows) ? thicknessRows : [])
    .map(row => {
      const firstTokenRow = Array.isArray(row?.row_tokens) && Array.isArray(row.row_tokens[0]) ? row.row_tokens[0] : [];
      const rawTokens = firstTokenRow.map(value => normalizeSelectionValue(value));
      const thicknessId = normalizeSelectionValue(row?.thickness_id ?? rawTokens[0]);
      if (!thicknessId) return null;
      return {
        thickness_id: thicknessId,
        material_id: normalizeSelectionValue(row?.material_id ?? rawTokens[2]) || '--',
        thickness_value: safeNumber(row?.thickness_value ?? row?.thickness_m ?? rawTokens[4], 0),
        raw_row_count: safeNumber(row?.raw_row_count, Array.isArray(row?.row_tokens) ? row.row_tokens.length : 0),
        raw_tokens_head: rawTokens.slice(0, 8),
      };
    })
    .filter(Boolean)
    .sort((a, b) => safeNumber(a.thickness_id, 0) - safeNumber(b.thickness_id, 0) || a.thickness_id.localeCompare(b.thickness_id));
}

export function buildRebarMaterialCodeSummary(rebarRows) {
  return (Array.isArray(rebarRows) ? rebarRows : [])
    .map((row, index) => {
      const tokens = (Array.isArray(row?.tokens) ? row.tokens : [])
        .map(value => normalizeSelectionValue(value))
        .filter(Boolean);
      const raw = normalizeSelectionValue(row?.raw);
      return {
        code_id: `rebar-${index + 1}`,
        material_code_label: tokens.join(' / ') || raw || '--',
        tokens: tokens.slice(0, 8),
        raw,
      };
    })
    .filter(row => row.material_code_label !== '--')
    .slice(0, 8);
}

function buildSignatureText(row = {}, keys = []) {
  const rawTokens = Array.isArray(row?.raw_tokens)
    ? row.raw_tokens.map(value => normalizeSelectionValue(value)).filter(Boolean)
    : [];
  return [
    ...keys.map(key => normalizeSelectionValue(row?.[key])),
    ...rawTokens,
  ].filter(Boolean).join('|');
}

export function buildMaterialModelSignature(modelPayload = {}) {
  const materialRows = (Array.isArray(modelPayload?.materials) ? modelPayload.materials : [])
    .map(row => {
      const materialId = normalizeSelectionValue(row?.id ?? row?.material_id);
      if (!materialId) return null;
      return {
        material_id: materialId,
        material_name: normalizeSelectionValue(row?.name || row?.material_name) || `Material ${materialId}`,
        signature: buildSignatureText(row, ['id', 'name', 'grade', 'material_name', 'material_grade']),
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.material_id.localeCompare(b.material_id, undefined, { numeric: true }));
  const sectionRows = (Array.isArray(modelPayload?.sections) ? modelPayload.sections : [])
    .map(row => {
      const sectionId = normalizeSelectionValue(row?.id ?? row?.section_id);
      if (!sectionId) return null;
      return {
        section_id: sectionId,
        section_name: normalizeSelectionValue(row?.name || row?.section_name) || `Section ${sectionId}`,
        signature: buildSignatureText(row, ['id', 'name', 'section_name']),
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.section_id.localeCompare(b.section_id, undefined, { numeric: true }));
  return {
    schema_version: 'structure-viewer-material-model-signature.v1',
    material_count: materialRows.length,
    section_count: sectionRows.length,
    element_count: Array.isArray(modelPayload?.elements) ? modelPayload.elements.length : 0,
    materials: materialRows,
    sections: sectionRows,
  };
}

export function buildReviewRowSummary(bridgeRows) {
  return (Array.isArray(bridgeRows) ? bridgeRows : [])
    .map(row => {
      const topRow = Array.isArray(row?.row_provenance_rows) ? row.row_provenance_rows[0] : {};
      return {
        review_case_id: normalizeSelectionValue(row?.review_case_id) || '--',
        member_id: normalizeSelectionValue(row?.baseline_focus_member_id || row?.review_member_id) || '',
        target_element_id: normalizeSelectionValue(row?.full_crosswalk_target_element_id),
        review_row_label: normalizeSelectionValue(row?.row_provenance_top_row_label) || '--',
        review_summary_label: normalizeSelectionValue(row?.row_provenance_summary_label) || '--',
        row_count: safeNumber(row?.row_provenance_row_count, Array.isArray(row?.row_provenance_rows) ? row.row_provenance_rows.length : 0),
        combination_count: safeNumber(row?.row_provenance_combination_count, 0),
        clause_count: safeNumber(row?.row_provenance_clause_count, 0),
        component_count: safeNumber(row?.row_provenance_component_count, 0),
        top_combination: normalizeSelectionValue(topRow?.combination),
        top_component: normalizeSelectionValue(topRow?.component),
        top_clause: normalizeSelectionValue(topRow?.clause),
        top_rule_family: normalizeSelectionValue(topRow?.rule_family),
        top_hazard_type: normalizeSelectionValue(topRow?.hazard_type || row?.source_hazard_type),
        top_topology_type: normalizeSelectionValue(topRow?.topology_type || row?.source_topology_type),
        top_demand: safeNumber(topRow?.demand, 0),
        top_capacity: safeNumber(topRow?.capacity, 0),
        top_dcr: safeNumber(topRow?.dcr, 0),
        combination_names: Array.isArray(row?.full_crosswalk_load_combination_names) ? row.full_crosswalk_load_combination_names.slice(0, 6) : [],
        component_names: Array.isArray(row?.row_provenance_component_names) ? row.row_provenance_component_names.slice(0, 8) : [],
        group_names: Array.isArray(row?.full_crosswalk_member_groups) ? row.full_crosswalk_member_groups.slice(0, 6) : [],
        isolation_token: buildReviewRowIsolationToken({
          review_case_id: row?.review_case_id,
          review_row_label: row?.row_provenance_top_row_label,
          member_id: row?.baseline_focus_member_id || row?.review_member_id,
          target_element_id: row?.full_crosswalk_target_element_id,
        }),
      };
    })
    .slice(0, 12);
}

export function buildLoadCombinationForceRows(bridgeRows) {
  return (Array.isArray(bridgeRows) ? bridgeRows : [])
    .flatMap(bridgeRow => {
      const rows = Array.isArray(bridgeRow?.row_provenance_rows) ? bridgeRow.row_provenance_rows : [];
      const focusMemberId = normalizeSelectionValue(bridgeRow?.baseline_focus_member_id || bridgeRow?.review_member_id);
      const targetElementId = normalizeSelectionValue(bridgeRow?.full_crosswalk_target_element_id);
      return rows.map(row => ({
        review_case_id: normalizeSelectionValue(row?.case_id || bridgeRow?.review_case_id) || '--',
        member_id: focusMemberId || normalizeSelectionValue(row?.member_id),
        source_member_id: normalizeSelectionValue(row?.member_id),
        target_element_id: targetElementId,
        member_type: normalizeSelectionValue(row?.member_type || bridgeRow?.source_member_type),
        combination: normalizeSelectionValue(row?.combination),
        combination_scale: safeNumber(row?.combination_scale, 1),
        component: normalizeSelectionValue(row?.component),
        clause: normalizeSelectionValue(row?.clause),
        rule_family: normalizeSelectionValue(row?.rule_family),
        hazard_type: normalizeSelectionValue(row?.hazard_type || bridgeRow?.source_hazard_type),
        topology_type: normalizeSelectionValue(row?.topology_type || bridgeRow?.source_topology_type),
        demand: safeNumber(row?.demand, 0),
        capacity: safeNumber(row?.capacity, 0),
        dcr: safeNumber(row?.dcr, 0),
      }));
    })
    .filter(row => row.combination && row.component && row.dcr > 0)
    .sort((a, b) => b.dcr - a.dcr || b.demand - a.demand || a.combination.localeCompare(b.combination))
    .slice(0, 2000);
}

export function extractLoadCaseInventory(modelPayload, metadata) {
  const labels = [];
  const pushLabel = value => {
    const label = normalizeSelectionValue(value);
    if (label && !labels.includes(label)) labels.push(label);
  };
  const loadPatternLibrary = metadata?.load_pattern_library && typeof metadata.load_pattern_library === 'object'
    ? metadata.load_pattern_library
    : {};
  const semanticRows = Array.isArray(loadPatternLibrary.case_semantic_rows) ? loadPatternLibrary.case_semantic_rows : [];
  semanticRows.forEach(row => pushLabel(row?.label || row?.case_name || row?.case_id || row?.pattern_id));
  const patternRows = Array.isArray(loadPatternLibrary.pattern_summary?.patterns) ? loadPatternLibrary.pattern_summary.patterns : [];
  patternRows.forEach(row => pushLabel(row?.label || row?.case_name || row?.pattern_id));
  const loads = Array.isArray(modelPayload?.loads) ? modelPayload.loads : [];
  loads.forEach(row => pushLabel(row?.case_name || row?.load_case_name || row?.name || row?.case_id));
  return labels;
}

export function extractLoadCombinationInventory(modelPayload, metadata) {
  const rows = [];
  const pushRow = row => {
    const name = normalizeSelectionValue(row?.name || row?.combination_name || row?.id);
    if (!name || rows.some(item => item.name === name)) return;
    const entryRows = Array.isArray(row?.entry_rows)
      ? row.entry_rows
      : Array.isArray(row?.entries)
        ? row.entries
        : [];
    const factorMap = row?.factor_map && typeof row.factor_map === 'object'
      ? row.factor_map
      : row?.expanded_factor_map && typeof row.expanded_factor_map === 'object'
        ? row.expanded_factor_map
        : {};
    rows.push({
      name,
      combination_type: normalizeSelectionValue(row?.combination_type) || 'GEN',
      limit_state: normalizeSelectionValue(row?.limit_state) || 'ACTIVE',
      expression: normalizeSelectionValue(row?.expression) || 'expression n/a',
      entry_count: safeNumber(row?.entry_count, entryRows.length),
      factor_map: { ...factorMap },
      referenced_combinations: Array.isArray(row?.referenced_combinations) ? row.referenced_combinations.filter(Boolean) : [],
      referenced_leaf_cases: Array.isArray(row?.referenced_leaf_cases) ? row.referenced_leaf_cases.filter(Boolean) : [],
      entry_rows: entryRows
        .filter(entry => entry && typeof entry === 'object')
        .map(entry => ({
          reference_kind: normalizeSelectionValue(entry?.reference_kind).toUpperCase() || 'ST',
          reference_name: normalizeSelectionValue(entry?.reference_name),
          factor: safeNumber(entry?.factor, 0),
        }))
        .filter(entry => entry.reference_name),
    });
  };
  const loadRows = Array.isArray(modelPayload?.loads?.load_combinations) ? modelPayload.loads.load_combinations : [];
  loadRows.forEach(pushRow);
  const editorSeed = metadata?.load_combination_editor_seed && typeof metadata.load_combination_editor_seed === 'object'
    ? metadata.load_combination_editor_seed
    : {};
  const seedRows = Array.isArray(editorSeed.combination_nodes) ? editorSeed.combination_nodes : [];
  seedRows.forEach(pushRow);
  return rows;
}

export function buildRealDrawingAssetRegistry(rootMeta) {
  return (Array.isArray(rootMeta?.real_drawing_asset_registry) ? rootMeta.real_drawing_asset_registry : [])
    .map(row => ({
      asset_ref: normalizeSelectionValue(row?.asset_ref),
      file_type: normalizeSelectionValue(row?.file_type),
      route: normalizeSelectionValue(row?.route),
      status: normalizeSelectionValue(row?.status),
      solver_exact: Boolean(row?.solver_exact),
      geometry_mode: normalizeSelectionValue(row?.geometry_mode),
      graph_source_kind: normalizeSelectionValue(row?.graph_source_kind),
      geometry_available: Boolean(row?.geometry_available),
      geometry_exact_ready: Boolean(row?.geometry_exact_ready),
      ifc_geometry_exact_ready: Boolean(row?.ifc_geometry_exact_ready),
      geometry_claim_status: normalizeSelectionValue(row?.geometry_claim_status),
      load_model_status: normalizeSelectionValue(row?.load_model_status),
      load_model_ready: Boolean(row?.load_model_ready),
      analysis_claim_ready: Boolean(row?.analysis_claim_ready),
      load_evidence_status: normalizeSelectionValue(row?.load_evidence_status),
      load_evidence_contract_pass: Boolean(row?.load_evidence_contract_pass),
      load_case_group_count: safeNumber(row?.load_case_group_count, 0),
      structural_load_count: safeNumber(row?.structural_load_count, 0),
      structural_action_count: safeNumber(row?.structural_action_count, 0),
      connected_structural_action_count: safeNumber(row?.connected_structural_action_count, 0),
      zero_load_signature_required: Boolean(row?.zero_load_signature_required),
      engineer_zero_load_signature_attached: Boolean(row?.engineer_zero_load_signature_attached),
      zero_load_attestation_scope: normalizeSelectionValue(row?.zero_load_attestation_scope),
      segment_count: safeNumber(row?.segment_count, 0),
      model_asset_count: safeNumber(row?.model_asset_count, 0),
      warning_label: normalizeSelectionValue(row?.warning_label),
      quality_flags: Array.isArray(row?.quality_flags)
        ? row.quality_flags.map(value => normalizeSelectionValue(value)).filter(Boolean)
        : [],
      source_quality_flags: Array.isArray(row?.source_quality_flags)
        ? row.source_quality_flags.map(value => normalizeSelectionValue(value)).filter(Boolean)
        : [],
      claim_quality_flags: Array.isArray(row?.claim_quality_flags)
        ? row.claim_quality_flags.map(value => normalizeSelectionValue(value)).filter(Boolean)
        : [],
      quality_notice: normalizeSelectionValue(row?.quality_notice),
      node_count: safeNumber(row?.node_count, 0),
      element_count: safeNumber(row?.element_count, 0),
      renderable_segment_count: safeNumber(row?.renderable_segment_count, row?.segment_count ?? 0),
      lod_evidence_status: normalizeSelectionValue(row?.lod_evidence_status),
      full_detail_segment_count: safeNumber(row?.full_detail_segment_count, 0),
      viewer_sample_segment_count: safeNumber(row?.viewer_sample_segment_count, 0),
      lod_sample_ratio: safeNumber(row?.lod_sample_ratio, 0),
    }))
    .filter(row => row.asset_ref)
    .slice(0, 128);
}

export function buildRealDrawingRegistrySummary(rootMeta, assetRegistry) {
  const summary = rootMeta?.real_drawing_registry_summary && typeof rootMeta.real_drawing_registry_summary === 'object'
    ? rootMeta.real_drawing_registry_summary
    : {};
  return {
    asset_count: safeNumber(summary.asset_count, rootMeta?.real_drawing_asset_count ?? assetRegistry.length),
    renderable_asset_count: safeNumber(summary.renderable_asset_count, rootMeta?.real_drawing_renderable_asset_count ?? 0),
    solver_exact_asset_count: safeNumber(summary.solver_exact_asset_count, rootMeta?.real_drawing_solver_exact_asset_count ?? 0),
    proxy_or_preview_asset_count: safeNumber(summary.proxy_or_preview_asset_count, rootMeta?.real_drawing_proxy_or_preview_asset_count ?? 0),
    route_counts: summary.route_counts && typeof summary.route_counts === 'object' ? { ...summary.route_counts } : {},
    status_counts: summary.status_counts && typeof summary.status_counts === 'object' ? { ...summary.status_counts } : {},
    quality_flag_counts: summary.quality_flag_counts && typeof summary.quality_flag_counts === 'object'
      ? { ...summary.quality_flag_counts }
      : {},
  };
}

function compactStringList(value, limit = 8) {
  return (Array.isArray(value) ? value : [])
    .map(item => normalizeSelectionValue(item))
    .filter(Boolean)
    .slice(0, limit);
}

function normalizeRealDrawingPromotionItem(row) {
  return {
    promotion_id: normalizeSelectionValue(row?.promotion_id),
    asset_ref: normalizeSelectionValue(row?.asset_ref),
    promotion_family: normalizeSelectionValue(row?.promotion_family),
    effort_label: normalizeSelectionValue(row?.effort_label),
    quality_tier: normalizeSelectionValue(row?.quality_tier),
    file_type: normalizeSelectionValue(row?.file_type),
    route: normalizeSelectionValue(row?.route),
    status: normalizeSelectionValue(row?.status),
    priority_rank: safeNumber(row?.priority_rank, 0),
    expected_solver_exact_delta: safeNumber(row?.expected_solver_exact_delta, 0),
    node_count: safeNumber(row?.node_count, 0),
    element_count: safeNumber(row?.element_count, 0),
    segment_count: safeNumber(row?.segment_count, 0),
    renderable_segment_count: safeNumber(row?.renderable_segment_count, 0),
    quality_flags: compactStringList(row?.quality_flags),
    closure_evidence_required: compactStringList(row?.closure_evidence_required),
    recommended_action: normalizeSelectionValue(row?.recommended_action),
    blocker_family: normalizeSelectionValue(row?.blocker_family),
    blocker_reason_code: normalizeSelectionValue(row?.blocker_reason_code),
    reconstruction_plan_status: normalizeSelectionValue(row?.reconstruction_plan_status),
    commercial_claim_blocked: Boolean(row?.commercial_claim_blocked),
    edge_coverage_ratio: safeNumber(row?.edge_coverage_ratio, 0),
  };
}

export function buildRealDrawingSolverExactPromotionQueue(rootMeta) {
  const queue = rootMeta?.real_drawing_solver_exact_promotion_queue && typeof rootMeta.real_drawing_solver_exact_promotion_queue === 'object'
    ? rootMeta.real_drawing_solver_exact_promotion_queue
    : {};
  const summary = queue.summary && typeof queue.summary === 'object' ? queue.summary : {};
  const plannedUnlockBatch = (Array.isArray(queue.planned_unlock_batch) ? queue.planned_unlock_batch : [])
    .map(normalizeRealDrawingPromotionItem)
    .filter(row => row.asset_ref)
    .slice(0, 32);
  const openPromotionItemsSource = Array.isArray(queue.open_promotion_items)
    ? queue.open_promotion_items
    : Array.isArray(queue.promotion_items)
      ? queue.promotion_items
      : [];
  const openPromotionItems = openPromotionItemsSource
    .map(normalizeRealDrawingPromotionItem)
    .filter(row => row.asset_ref)
    .slice(0, 32);
  if (!Object.keys(queue).length && !plannedUnlockBatch.length && !openPromotionItems.length) return {};
  return {
    schema_version: normalizeSelectionValue(queue.schema_version),
    contract_pass: Boolean(queue.contract_pass),
    reason_code: normalizeSelectionValue(queue.reason_code),
    quality_gate_reason_code: normalizeSelectionValue(queue.quality_gate_reason_code),
    structure_viewer_href: normalizeSelectionValue(queue.structure_viewer_href),
    recommended_claim: normalizeSelectionValue(queue.recommended_claim),
    summary: {
      current_solver_exact_asset_count: safeNumber(summary.current_solver_exact_asset_count, 0),
      target_solver_exact_asset_count: safeNumber(summary.target_solver_exact_asset_count, 0),
      required_solver_exact_delta: safeNumber(summary.required_solver_exact_delta, 0),
      planned_unlock_batch_count: safeNumber(summary.planned_unlock_batch_count, plannedUnlockBatch.length),
      planned_unlock_batch_expected_delta: safeNumber(summary.planned_unlock_batch_expected_delta, 0),
      planned_solver_exact_asset_count_after_unlock_batch: safeNumber(
        summary.planned_solver_exact_asset_count_after_unlock_batch,
        0
      ),
      promotion_candidate_count: safeNumber(summary.promotion_candidate_count, plannedUnlockBatch.length),
      promotion_delta_available: safeNumber(summary.promotion_delta_available, 0),
      sufficient_unlock_batch_for_target: Boolean(summary.sufficient_unlock_batch_for_target),
      family_counts: summary.family_counts && typeof summary.family_counts === 'object' ? { ...summary.family_counts } : {},
      effort_counts: summary.effort_counts && typeof summary.effort_counts === 'object' ? { ...summary.effort_counts } : {},
    },
    planned_unlock_batch: plannedUnlockBatch,
    open_promotion_items: openPromotionItems,
  };
}

export function buildDirectModelMeta(rootPayload, modelPayload, sourceMeta = {}) {
  const metadata = modelPayload?.metadata && typeof modelPayload.metadata === 'object' ? modelPayload.metadata : {};
  const rootMeta = rootPayload?.meta && typeof rootPayload.meta === 'object' ? rootPayload.meta : {};
  const sourceInfo = rootPayload?.source && typeof rootPayload.source === 'object' ? rootPayload.source : {};
  const axisBridge = metadata.kds_geometry_bridge && typeof metadata.kds_geometry_bridge === 'object' ? metadata.kds_geometry_bridge : {};
  const axisRefs = axisBridge.axis_refs && typeof axisBridge.axis_refs === 'object' ? axisBridge.axis_refs : {};
  const sectionLibrary = metadata.section_library && typeof metadata.section_library === 'object' ? metadata.section_library : {};
  const sectionSummary = sectionLibrary.summary && typeof sectionLibrary.summary === 'object' ? sectionLibrary.summary : {};
  const loadPatternLibrary = metadata.load_pattern_library && typeof metadata.load_pattern_library === 'object' ? metadata.load_pattern_library : {};
  const loadPatternSummary = loadPatternLibrary.summary && typeof loadPatternLibrary.summary === 'object'
    ? loadPatternLibrary.summary
    : (loadPatternLibrary.pattern_summary && typeof loadPatternLibrary.pattern_summary === 'object' ? loadPatternLibrary.pattern_summary : {});
  const storySlices = Array.isArray(axisRefs.z)
    ? axisRefs.z.map(row => normalizeSelectionValue(row?.label || row?.name || row?.axis_label || row?.id)).filter(Boolean)
    : [];
  const reviewSummary = axisBridge.summary && typeof axisBridge.summary === 'object' ? axisBridge.summary : {};
  const sectionUsageRows = Array.isArray(sectionLibrary.usage_summary) ? sectionLibrary.usage_summary : [];
  const sectionCatalogSummary = buildSectionCatalogSummary(
    modelPayload?.sections,
    sectionUsageRows,
    modelPayload?.elements,
    modelPayload?.materials,
    metadata
  );
  const materialCatalogSummary = buildMaterialCatalogSummary(
    modelPayload?.materials,
    modelPayload?.elements,
    { ...metadata, section_rows: modelPayload?.sections }
  );
  const materialModelSignature = buildMaterialModelSignature(modelPayload);
  const materialFamilyCoverageSummary = buildMaterialFamilyCoverageSummary(materialCatalogSummary);
  const thicknessCatalogSummary = buildThicknessCatalogSummary(metadata.thickness);
  const rebarMaterialCodeSummary = buildRebarMaterialCodeSummary(metadata.rebar_material_codes);
  const bridgeRows = Array.isArray(axisBridge.bridge_rows) ? axisBridge.bridge_rows : [];
  const loadCombinationForceRows = buildLoadCombinationForceRows(bridgeRows);
  const groupRows = Array.isArray(metadata.groups) ? metadata.groups : [];
  const realDrawingAssetRegistry = buildRealDrawingAssetRegistry(rootMeta);
  const realDrawingRegistrySummary = buildRealDrawingRegistrySummary(rootMeta, realDrawingAssetRegistry);
  const realDrawingSolverExactPromotionQueue = buildRealDrawingSolverExactPromotionQueue(rootMeta);
  const sectionCount = safeNumber(sectionSummary.section_row_count, Array.isArray(modelPayload?.sections) ? modelPayload.sections.length : 0);
  const usedSectionCount = safeNumber(sectionSummary.used_section_count, 0);
  const materialCount = Array.isArray(modelPayload?.materials) ? modelPayload.materials.length : materialCatalogSummary.length;
  const usedMaterialCount = materialCatalogSummary.filter(row => safeNumber(row.usage_count, 0) > 0).length;
  const axisLabelCount =
    (Array.isArray(axisRefs.x) ? axisRefs.x.length : 0) +
    (Array.isArray(axisRefs.y) ? axisRefs.y.length : 0) +
    (Array.isArray(axisRefs.z) ? axisRefs.z.length : 0);
  const structureTypeLabel = normalizeSelectionValue(
    Array.isArray(metadata.structure_type) && metadata.structure_type[0]?.raw
      ? metadata.structure_type[0].raw
      : (rootPayload?.source || rootPayload?.parser || 'MIDAS parsed model')
  );
  const lengthUnitsLabel = normalizeSelectionValue(
    Array.isArray(metadata.length_units) && metadata.length_units[0]?.raw ? metadata.length_units[0].raw : ''
  );
  return {
    name: String(rootPayload?.run_id || rootPayload?.source || sourceMeta.label || 'MIDAS parsed model'),
    stories: estimateStoryCount(modelPayload?.nodes, axisRefs) || '--',
    story_slices: storySlices,
    load_case_inventory: extractLoadCaseInventory(modelPayload, metadata),
    load_combination_inventory: extractLoadCombinationInventory(modelPayload, metadata),
    source_mode: String(sourceMeta.mode || 'direct_payload'),
    source_label: String(sourceMeta.label || sourceInfo.path || rootPayload?.source || 'MIDAS parsed model'),
    source_path: String(sourceMeta.resolvedPath || sourceInfo.path || ''),
    source_artifact_sha256: String(sourceInfo.sha256 || ''),
    source_artifact_size_bytes: safeNumber(sourceInfo.size_bytes, 0),
    source_artifact_format: String(sourceInfo.format || ''),
    source_artifact_family: String(sourceInfo.source_family || ''),
    loaded_at: String(sourceMeta.loadedAt || ''),
    generated_at: String(rootPayload?.generated_at || ''),
    parser_label: String(rootPayload?.parser || ''),
    structure_type_label: structureTypeLabel || '--',
    length_units_label: lengthUnitsLabel || '--',
    group_count: Array.isArray(metadata.groups) ? metadata.groups.length : 0,
    member_count: Array.isArray(metadata.members) ? metadata.members.length : 0,
    material_count: materialCount,
    used_material_count: usedMaterialCount,
    material_family_coverage_summary: materialFamilyCoverageSummary,
    material_model_signature: materialModelSignature,
    material_family_ontology_count: materialFamilyCoverageSummary.ontology_family_count,
    material_family_count: materialFamilyCoverageSummary.family_count,
    known_material_family_count: materialFamilyCoverageSummary.known_family_count,
    unclassified_material_count: materialFamilyCoverageSummary.unclassified_material_count,
    material_missing_definition_count: materialFamilyCoverageSummary.missing_definition_count,
    section_count: sectionCount,
    used_section_count: usedSectionCount,
    thickness_count: thicknessCatalogSummary.length,
    material_section_schedule_count: materialCatalogSummary.reduce(
      (sum, row) => sum + (Array.isArray(row?.section_usage_summary) ? row.section_usage_summary.length : 0),
      0
    ),
    section_material_schedule_count: sectionCatalogSummary.reduce(
      (sum, row) => sum + (Array.isArray(row?.material_usage_summary) ? row.material_usage_summary.length : 0),
      0
    ),
    geometry_bridge_review_count: safeNumber(reviewSummary.review_id_count, 0),
    geometry_bridge_mapped_review_count: safeNumber(reviewSummary.mapped_review_id_count, 0),
    geometry_bridge_full_member_crosswalk_count: safeNumber(reviewSummary.full_member_crosswalk_count, 0),
    load_pattern_count: safeNumber(
      loadPatternSummary.pattern_count,
      Array.isArray(loadPatternLibrary.case_semantic_rows) ? loadPatternLibrary.case_semantic_rows.length : 0
    ),
    load_pattern_primitive_count: safeNumber(loadPatternSummary.primitive_count, 0),
    axis_label_count: axisLabelCount,
    axis_ref_source_mode: String(axisBridge.axis_ref_source_mode || 'none'),
    axis_ref_note: String(axisBridge.axis_ref_note || ''),
    material_catalog_summary: materialCatalogSummary,
    thickness_catalog_summary: thicknessCatalogSummary,
    rebar_material_code_summary: rebarMaterialCodeSummary,
    section_catalog_summary: sectionCatalogSummary,
    section_family_summary: buildSectionFamilySummary(sectionCatalogSummary),
    group_summary: buildGroupSummary(groupRows),
    review_row_summary: buildReviewRowSummary(bridgeRows),
    load_combination_force_rows: loadCombinationForceRows,
    load_combination_force_row_count: loadCombinationForceRows.length,
    real_drawing_asset_count: realDrawingRegistrySummary.asset_count,
    real_drawing_renderable_asset_count: realDrawingRegistrySummary.renderable_asset_count,
    real_drawing_solver_exact_asset_count: realDrawingRegistrySummary.solver_exact_asset_count,
    real_drawing_proxy_or_preview_asset_count: realDrawingRegistrySummary.proxy_or_preview_asset_count,
    real_drawing_registry_summary: realDrawingRegistrySummary,
    real_drawing_asset_registry: realDrawingAssetRegistry,
    real_drawing_solver_exact_promotion_queue: realDrawingSolverExactPromotionQueue,
  };
}

function buildDirectModelLookupContext(modelPayload) {
  const metadata = modelPayload.metadata && typeof modelPayload.metadata === 'object' ? modelPayload.metadata : {};
  const sectionRows = Array.isArray(modelPayload.sections) ? modelPayload.sections : [];
  const sectionDescriptorById = buildSectionDescriptorIndex({ ...metadata, section_rows: sectionRows });
  const sectionById = new Map(sectionRows.map(row => {
    const sectionId = String(row?.id);
    const descriptor = sectionDescriptorById.get(sectionId) || {};
    return [sectionId, String(descriptor.section_label || row?.name || row?.label || row?.section_name || `Section ${row?.id ?? '--'}`)];
  }));
  const materialCatalogSummary = buildMaterialCatalogSummary(
    modelPayload.materials,
    modelPayload.elements,
    { ...metadata, section_rows: modelPayload.sections }
  );
  const materialById = new Map(materialCatalogSummary.map(row => [String(row?.material_id), row]));
  const materialColorById = new Map(
    (Array.isArray(metadata.material_colors) ? metadata.material_colors : [])
      .map(row => [String(row?.material_id), rgbArrayToHex(row?.fill_rgb || row?.wire_rgb)])
      .filter(([, hex]) => Boolean(hex))
  );
  const sectionUsageById = new Map(
    (Array.isArray(metadata.section_library?.usage_summary) ? metadata.section_library.usage_summary : [])
      .map(row => [String(row?.section_id), row])
  );
  const sectionColorById = new Map(
    (Array.isArray(metadata.section_colors) ? metadata.section_colors : [])
      .map(row => [String(row?.section_id), rgbArrayToHex(row?.fill_rgb || row?.wire_rgb)])
      .filter(([, hex]) => Boolean(hex))
  );
  const memberByElementId = new Map();
  (Array.isArray(metadata.members) ? metadata.members : []).forEach(member => {
    const memberId = normalizeSelectionValue(member?.id);
    const elementIds = Array.isArray(member?.element_ids) ? member.element_ids : [];
    elementIds.forEach(elementId => memberByElementId.set(String(elementId), memberId));
  });
  const groupsByElementId = new Map();
  (Array.isArray(metadata.groups) ? metadata.groups : []).forEach(group => {
    const groupName = normalizeSelectionValue(group?.name);
    if (!groupName) return;
    const elementIds = Array.isArray(group?.element_ids) ? group.element_ids : [];
    elementIds.forEach(elementId => {
      const key = String(elementId);
      const current = groupsByElementId.get(key) || [];
      if (!current.includes(groupName)) current.push(groupName);
      groupsByElementId.set(key, current);
    });
  });
  const reviewByMemberId = new Map();
  const reviewByElementId = new Map();
  (Array.isArray(metadata.kds_geometry_bridge?.bridge_rows) ? metadata.kds_geometry_bridge.bridge_rows : []).forEach(row => {
    const memberId = normalizeSelectionValue(row?.baseline_focus_member_id || row?.review_member_id);
    if (!memberId || reviewByMemberId.has(memberId)) return;
    reviewByMemberId.set(memberId, row);
  });
  (Array.isArray(metadata.kds_geometry_bridge?.bridge_rows) ? metadata.kds_geometry_bridge.bridge_rows : []).forEach(row => {
    const elementId = normalizeSelectionValue(row?.full_crosswalk_target_element_id);
    if (!elementId || reviewByElementId.has(elementId)) return;
    reviewByElementId.set(elementId, row);
  });
  return {
    groupsByElementId,
    materialById,
    materialColorById,
    memberByElementId,
    reviewByElementId,
    reviewByMemberId,
    sectionById,
    sectionColorById,
    sectionDescriptorById,
    sectionUsageById,
  };
}

function sanitizeDirectNode(node, idx) {
  return {
    id: node?.id ?? idx,
    x: safeNumber(node?.x, 0),
    y: safeNumber(node?.y, 0),
    z: safeNumber(node?.z, 0),
    dx: safeNumber(node?.dx, 0),
    dy: safeNumber(node?.dy, 0),
    dz: safeNumber(node?.dz, 0),
    disp_mag: safeNumber(node?.disp_mag, 0),
    stress_vm: safeNumber(node?.stress_vm, 0),
    dcr: safeNumber(node?.dcr, 0),
    axial: safeNumber(node?.axial, 0),
    moment: safeNumber(node?.moment, 0),
    shear: safeNumber(node?.shear, 0),
  };
}

function sanitizeDirectElement(element, idx, context) {
  const memberId = normalizeSelectionValue(element?.member_id) || context.memberByElementId.get(String(element?.id ?? idx)) || '';
  const materialId = normalizeSelectionValue(element?.material_id ?? element?.materialId ?? element?.material);
  const materialRow = context.materialById.get(materialId) || {};
  const reviewRow = context.reviewByMemberId.get(memberId) || context.reviewByElementId.get(normalizeSelectionValue(element?.id ?? idx)) || null;
  const groupNames = context.groupsByElementId.get(String(element?.id ?? idx)) || [];
  const materialName = normalizeSelectionValue(element?.material_name || element?.material || materialRow.material_name) || '--';
  const materialGrade = normalizeSelectionValue(element?.material_grade || materialRow.material_grade) || '--';
  const materialFamily = knownMaterialFamily(element?.material_family)
    || normalizeSelectionValue(materialRow.material_family)
    || inferMaterialFamily({ material_name: materialName, material_grade: materialGrade, material_label: element?.material_label });
  const sectionId = normalizeSelectionValue(element?.section_id);
  const sectionDescriptor = context.sectionDescriptorById.get(sectionId) || {};
  const sectionUsageRow = context.sectionUsageById.get(sectionId) || {};
  return {
    ...element,
    id: element?.id ?? idx,
    type: normalizeElementType(element?.family || element?.type),
    node_ids: Array.isArray(element?.node_ids) ? element.node_ids : [],
    member_id: memberId,
    material_id: materialId || normalizeSelectionValue(materialRow.material_id),
    material_name: materialName,
    material_grade: materialGrade,
    material_label: normalizeSelectionValue(materialRow.material_label) || (materialGrade === '--' ? materialName : `${materialName} ${materialGrade}`),
    material_family: materialFamily || '--',
    material_family_label: normalizeSelectionValue(element?.material_family_label || materialRow.material_family_label)
      || MATERIAL_FAMILY_LABEL_BY_ID.get(materialFamily)
      || materialFamily
      || '--',
    material_family_known: materialFamily !== 'unclassified' && Boolean(materialFamily),
    material_elastic_modulus: safeNumber(element?.material_elastic_modulus, safeNumber(materialRow.elastic_modulus, 0)),
    material_poisson_ratio: safeNumber(element?.material_poisson_ratio, safeNumber(materialRow.poisson_ratio, 0)),
    material_density: safeNumber(element?.material_density, safeNumber(materialRow.density, 0)),
    material_usage_count: safeNumber(materialRow.usage_count, 0),
    material_source_status: normalizeSelectionValue(materialRow.source_status) || 'missing_material_definition',
    material_color: String(element?.material_color || context.materialColorById.get(materialId) || '').trim(),
    section: String(element?.section || context.sectionById.get(sectionId) || '--'),
    section_family: normalizeSelectionValue(sectionUsageRow?.inferred_family || sectionDescriptor.section_family) || '--',
    section_shape: normalizeSelectionValue(sectionUsageRow?.inferred_shape || sectionDescriptor.section_shape) || '--',
    group_names: groupNames,
    group_label: groupNames.join(', ') || '--',
    review_case_id: normalizeSelectionValue(reviewRow?.review_case_id) || '--',
    review_row_label: normalizeSelectionValue(reviewRow?.row_provenance_top_row_label) || '--',
    review_summary_label: normalizeSelectionValue(reviewRow?.row_provenance_summary_label) || '--',
    review_combination_label: Array.isArray(reviewRow?.full_crosswalk_load_combination_names)
      ? reviewRow.full_crosswalk_load_combination_names.slice(0, 4).join(', ')
      : '--',
    dcr: safeNumber(element?.dcr, safeNumber(element?.max_dcr_after, safeNumber(element?.max_dcr_before, 0))),
    axial: safeNumber(element?.axial, 0),
    moment: safeNumber(element?.moment, 0),
    shear: safeNumber(element?.shear, 0),
    color: String(element?.color || context.sectionColorById.get(String(element?.section_id)) || context.materialColorById.get(materialId) || '').trim(),
  };
}

function buildSanitizedDirectModel(payload, sourceMeta, nodes, elements, normalizationMode) {
  const extracted = extractModelPayload(payload);
  const modelPayload = extracted?.model || {};
  const rootPayload = extracted?.root || payload || {};
  return {
    nodes,
    elements,
    meta: {
      ...(rootPayload.meta && typeof rootPayload.meta === 'object' ? rootPayload.meta : {}),
      ...buildDirectModelMeta(rootPayload, modelPayload, sourceMeta),
      normalization_mode: normalizationMode,
    },
  };
}

export function sanitizeModelPayload(payload, sourceMeta = {}) {
  const extracted = extractModelPayload(payload);
  const modelPayload = extracted?.model || {};
  const context = buildDirectModelLookupContext(modelPayload);
  const nodes = (modelPayload.nodes || []).map(sanitizeDirectNode);
  const elements = (modelPayload.elements || []).map((element, idx) => sanitizeDirectElement(element, idx, context));
  return buildSanitizedDirectModel(payload, sourceMeta, nodes, elements, 'direct');
}

export async function sanitizeModelPayloadAsync(payload, sourceMeta = {}, {
  processInChunks,
  chunkSize = DEFAULT_NORMALIZATION_CHUNK_SIZE,
} = {}) {
  const extracted = extractModelPayload(payload);
  const modelPayload = extracted?.model || {};
  const context = buildDirectModelLookupContext(modelPayload);
  const chunker = typeof processInChunks === 'function'
    ? processInChunks
    : async (rows, handler) => {
      (Array.isArray(rows) ? rows : []).forEach((row, index) => handler(row, index, index));
    };
  const mapRows = async (rows, mapper, options = {}) => {
    const out = [];
    await chunker(rows, (item, index, globalIndex) => {
      const mapped = mapper(item, index, globalIndex);
      if (mapped !== null && mapped !== undefined) out.push(mapped);
    }, { chunkSize, ...options });
    return out;
  };
  const nodes = await mapRows(modelPayload.nodes || [], sanitizeDirectNode, { progressLabel: 'Normalizing nodes' });
  const elements = await mapRows(modelPayload.elements || [], (element, idx) => sanitizeDirectElement(element, idx, context), {
    progressLabel: 'Normalizing elements',
  });
  return buildSanitizedDirectModel(payload, sourceMeta, nodes, elements, 'chunked');
}
