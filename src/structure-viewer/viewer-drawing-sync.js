/**
 * Drawing-to-Viewport sync engine.
 *
 * Provides bidirectional selection sync between:
 * - 2D SVG structural drawings (plan, elevation, isometric)
 * - 3D Structure Viewer (Three.js viewport)
 *
 * Selection in either surface focuses the same member in the other.
 * Hover previews and deep-link state are maintained consistently.
 */

const DRAWING_SYNC_CHANNEL = 'structural-drawing-sync-v1';

class DrawingViewportSync {
  constructor({
    viewportSelectionApi = null,
    svgContainerSelector = '#svg-drawing-container',
    viewportContainerSelector = '#viewport',
    onViewportSelect = null,
    onDrawingSelect = null,
  } = {}) {
    this.viewportSelectionApi = viewportSelectionApi;
    this.svgContainer = document.querySelector(svgContainerSelector);
    this.viewportContainer = document.querySelector(viewportContainerSelector);
    this.onViewportSelect = onViewportSelect;
    this.onDrawingSelect = onDrawingSelect;
    this.svgDoc = null;
    this.activeMemberId = '';
    this.activeElementId = '';
    this.hoverMemberId = '';
    this.drawingScale = 1;
    this.drawingOffset = { x: 0, y: 0 };
    this.memberIdToSvgElements = new Map();
    this.memberIdToViewportMesh = new Map();
    this.isSyncing = false;
    this.channel = null;
    this._initBroadcastChannel();
    this._initSvgListeners();
  }

  _initBroadcastChannel() {
    try {
      if (typeof BroadcastChannel === 'function') {
        this.channel = new BroadcastChannel(DRAWING_SYNC_CHANNEL);
        this.channel.onmessage = (event) => this._handleExternalSync(event.data);
      }
    } catch (_err) {
      // noop
    }
  }

  _initSvgListeners() {
    if (!this.svgContainer) return;
    this.svgContainer.addEventListener('click', (e) => this._onSvgClick(e));
    this.svgContainer.addEventListener('mouseover', (e) => this._onSvgHover(e));
    this.svgContainer.addEventListener('mouseout', () => this._clearSvgHover());
  }

  loadSvgContent(svgText) {
    if (!this.svgContainer) return;
    this.svgContainer.innerHTML = svgText;
    const svg = this.svgContainer.querySelector('svg');
    if (!svg) return;
    this.svgDoc = svg;
    this._indexSvgMemberElements();
    this._applyDrawingTransforms();
  }

  loadSvgFromUrl(url) {
    return fetch(url)
      .then(r => r.text())
      .then(text => this.loadSvgContent(text));
  }

  _indexSvgMemberElements() {
    this.memberIdToSvgElements.clear();
    if (!this.svgDoc) return;
    const elements = this.svgDoc.querySelectorAll('[data-member-id], [member-id], [id^="member-"], [id^="M-"], [id^="MF-"]');
    elements.forEach(el => {
      const memberId = el.getAttribute('data-member-id') ||
                        el.getAttribute('member-id') ||
                        el.id?.replace(/^member-/, '')?.replace(/^M-/, '')?.replace(/^MF-/, '');
      if (!memberId) return;
      if (!this.memberIdToSvgElements.has(memberId)) {
        this.memberIdToSvgElements.set(memberId, []);
      }
      this.memberIdToSvgElements.get(memberId).push(el);
    });
  }

  _applyDrawingTransforms() {
    if (!this.svgDoc) return;
    const viewBox = this.svgDoc.viewBox.baseVal;
    if (!viewBox || !viewBox.width) return;
    const rect = this.svgContainer.getBoundingClientRect();
    const scaleX = rect.width / viewBox.width;
    const scaleY = rect.height / viewBox.height;
    this.drawingScale = Math.min(scaleX, scaleY);
    this.drawingOffset = {
      x: (rect.width - viewBox.width * this.drawingScale) / 2 - viewBox.x * this.drawingScale,
      y: (rect.height - viewBox.height * this.drawingScale) / 2 - viewBox.y * this.drawingScale,
    };
  }

  _onSvgClick(event) {
    const target = event.target.closest('[data-member-id], [member-id], [id^="member-"], [id^="M-"], [id^="MF-"]');
    if (!target) {
      this.clearSelection();
      return;
    }
    const memberId = target.getAttribute('data-member-id') ||
                      target.getAttribute('member-id') ||
                      target.id?.replace(/^member-/, '')?.replace(/^M-/, '')?.replace(/^MF-/, '');
    if (!memberId) return;
    this.selectMember(memberId, { source: 'drawing' });
  }

  _onSvgHover(event) {
    const target = event.target.closest('[data-member-id], [member-id], [id^="member-"], [id^="M-"], [id^="MF-"]');
    if (!target) {
      this._clearSvgHover();
      return;
    }
    const memberId = target.getAttribute('data-member-id') ||
                      target.getAttribute('member-id') ||
                      target.id?.replace(/^member-/, '')?.replace(/^M-/, '')?.replace(/^MF-/, '');
    if (memberId && memberId !== this.hoverMemberId) {
      this.hoverMemberId = memberId;
      this._highlightSvgMember(memberId, { kind: 'hover' });
      this._publishSync({ kind: 'hover', memberId, source: 'drawing' });
    }
  }

  _clearSvgHover() {
    if (!this.hoverMemberId) return;
    this._unhighlightSvgMember(this.hoverMemberId, { kind: 'hover' });
    this.hoverMemberId = '';
    this._publishSync({ kind: 'hover-clear', source: 'drawing' });
  }

  selectMember(memberId, { source = 'api', scrollIntoView = true } = {}) {
    if (!memberId || this.isSyncing) return;
    this.isSyncing = true;
    this.activeMemberId = String(memberId);

    // Update drawing
    this._clearAllDrawingHighlights();
    this._highlightSvgMember(this.activeMemberId, { kind: 'select' });

    // Update viewport via API
    if (this.viewportSelectionApi && typeof this.viewportSelectionApi.selectByMemberId === 'function') {
      this.viewportSelectionApi.selectByMemberId(this.activeMemberId);
    }

    // Callbacks
    if (source === 'drawing' && this.onDrawingSelect) {
      this.onDrawingSelect(this.activeMemberId);
    }
    if (source === 'viewport' && this.onViewportSelect) {
      this.onViewportSelect(this.activeMemberId);
    }

    // Broadcast
    this._publishSync({ kind: 'select', memberId: this.activeMemberId, source });

    // Scroll drawing into view
    if (scrollIntoView) {
      this._scrollDrawingToMember(this.activeMemberId);
    }

    this.isSyncing = false;
  }

  selectElement(elementId, memberId, { source = 'api' } = {}) {
    if (!elementId) return;
    this.activeElementId = String(elementId);
    if (memberId) this.activeMemberId = String(memberId);
    this._publishSync({ kind: 'select-element', elementId, memberId: this.activeMemberId, source });
  }

  clearSelection() {
    this.activeMemberId = '';
    this.activeElementId = '';
    this._clearAllDrawingHighlights();
    this._publishSync({ kind: 'clear', source: 'api' });
  }

  _highlightSvgMember(memberId, { kind = 'select' } = {}) {
    const elements = this.memberIdToSvgElements.get(memberId);
    if (!elements) return;
    const strokeColor = kind === 'select' ? '#38bdf8' : '#fbbf24';
    const strokeWidth = kind === 'select' ? 3 : 2;
    elements.forEach(el => {
      el.dataset.originalStroke = el.dataset.originalStroke || el.getAttribute('stroke') || 'none';
      el.dataset.originalStrokeWidth = el.dataset.originalStrokeWidth || el.getAttribute('stroke-width') || '1';
      el.setAttribute('stroke', strokeColor);
      el.setAttribute('stroke-width', String(strokeWidth));
      if (kind === 'select') {
        el.style.filter = 'drop-shadow(0 0 3px rgba(56,189,248,0.5))';
      }
    });
  }

  _unhighlightSvgMember(memberId, { kind = 'select' } = {}) {
    const elements = this.memberIdToSvgElements.get(memberId);
    if (!elements) return;
    elements.forEach(el => {
      const origStroke = el.dataset.originalStroke;
      const origWidth = el.dataset.originalStrokeWidth;
      if (origStroke !== undefined) el.setAttribute('stroke', origStroke);
      if (origWidth !== undefined) el.setAttribute('stroke-width', origWidth);
      if (kind === 'select') el.style.filter = '';
    });
  }

  _clearAllDrawingHighlights() {
    this.memberIdToSvgElements.forEach((elements, memberId) => {
      this._unhighlightSvgMember(memberId, { kind: 'select' });
      this._unhighlightSvgMember(memberId, { kind: 'hover' });
    });
  }

  _scrollDrawingToMember(memberId) {
    const elements = this.memberIdToSvgElements.get(memberId);
    if (!elements || !elements.length || !this.svgContainer) return;
    const first = elements[0];
    const svgRect = this.svgContainer.getBoundingClientRect();
    const elRect = first.getBoundingClientRect();
    const scrollX = elRect.left - svgRect.left - svgRect.width / 2 + elRect.width / 2;
    const scrollY = elRect.top - svgRect.top - svgRect.height / 2 + elRect.height / 2;
    this.svgContainer.scrollBy({ left: scrollX, top: scrollY, behavior: 'smooth' });
  }

  _publishSync(message) {
    try {
      this.channel?.postMessage(message);
    } catch (_err) {
      // noop
    }
  }

  _handleExternalSync(message) {
    if (!message || message.source === 'api') return;
    if (message.kind === 'select' && message.memberId) {
      this.selectMember(message.memberId, { source: 'external', scrollIntoView: false });
    } else if (message.kind === 'hover' && message.memberId) {
      this._highlightSvgMember(message.memberId, { kind: 'hover' });
    } else if (message.kind === 'hover-clear') {
      if (this.hoverMemberId) this._unhighlightSvgMember(this.hoverMemberId, { kind: 'hover' });
    } else if (message.kind === 'clear') {
      this.clearSelection();
    }
  }

  syncViewportToDrawing(viewportEvent) {
    // Called when a mesh is selected in the 3D viewport
    if (!viewportEvent || !viewportEvent.memberId) return;
    this.selectMember(viewportEvent.memberId, { source: 'viewport' });
  }

  destroy() {
    if (this.channel) {
      this.channel.close();
      this.channel = null;
    }
  }
}

/**
 * Sync a member highlight from the viewport to the drawing rail.
 * This is a lightweight helper for the existing index.html selection system.
 */
export function syncViewportSelectionToDrawing(memberId, drawingSyncInstance) {
  if (!drawingSyncInstance || !memberId) return;
  drawingSyncInstance.selectMember(memberId, { source: 'viewport' });
}

/**
 * Create a drawing thumbnail preview from a 3D model bounding box.
 */
export function generateDrawingPreviewUrl(modelData, { view = 'plan', level = 0 } = {}) {
  if (!modelData || !Array.isArray(modelData.nodes)) return '';
  const nodes = modelData.nodes;
  const levels = [...new Set(nodes.map(n => n.z).filter(Number.isFinite))].sort((a, b) => a - b);
  const targetZ = levels[level] || 0;
  const levelNodes = nodes.filter(n => Math.abs(n.z - targetZ) < 0.5);
  if (!levelNodes.length) return '';

  const xs = levelNodes.map(n => n.x);
  const ys = levelNodes.map(n => n.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  const margin = 5;
  const width = Math.max(maxX - minX + margin * 2, 100);
  const height = Math.max(maxY - minY + margin * 2, 100);

  const svgParts = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="${minX - margin} ${minY - margin} ${width} ${height}">`,
    `<rect x="${minX - margin}" y="${minY - margin}" width="${width}" height="${height}" fill="#0f172a"/>`,
  ];

  // Draw members at this level
  if (Array.isArray(modelData.elements)) {
    modelData.elements.forEach(el => {
      const nodeIds = el.node_ids || [];
      const elNodes = nodeIds.map(id => nodes.find(n => n.id === id)).filter(Boolean);
      if (elNodes.length === 2) {
        const atLevel = elNodes.every(n => Math.abs(n.z - targetZ) < 0.5);
        if (atLevel) {
          const color = el.type === 'column' ? '#f87171' : el.type === 'beam' ? '#38bdf8' : '#94a3b8';
          svgParts.push(`<line x1="${elNodes[0].x}" y1="${elNodes[0].y}" x2="${elNodes[1].x}" y2="${elNodes[1].y}" stroke="${color}" stroke-width="2" data-member-id="${el.member_id || el.id}"/>`);
        }
      }
    });
  }

  svgParts.push('</svg>');
  return `data:image/svg+xml;base64,${btoa(svgParts.join(''))}`;
}

export { DrawingViewportSync };
export default DrawingViewportSync;
