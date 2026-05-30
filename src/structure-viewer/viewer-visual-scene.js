/**
 * Commercial-grade viewport visuals: IBL, infinite grid, selection outline,
 * view cube, technical drawing mode, quality tiers.
 */

let sharedEnvironmentMap = null;

export function getViewerEnvironmentMap() {
  return sharedEnvironmentMap;
}

function createRoomEnvironmentScene(THREE) {
  const scene = new THREE.Scene();
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const createPanel = (color, intensity, position, rotation) => {
    const material = new THREE.MeshStandardMaterial({
      color,
      metalness: 0,
      roughness: 1,
      envMapIntensity: 0,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.copy(position);
    mesh.rotation.copy(rotation);
    mesh.scale.setScalar(intensity);
    mesh.material = mesh.material.clone();
    mesh.material.emissive = new THREE.Color(color);
    mesh.material.emissiveIntensity = intensity;
    scene.add(mesh);
  };
  createPanel(0xffffff, 1.2, new THREE.Vector3(0, 1.2, 0), new THREE.Euler(0, 0, 0));
  createPanel(0x4a6a8a, 0.6, new THREE.Vector3(-1.2, 0, 0), new THREE.Euler(0, Math.PI / 2, 0));
  createPanel(0x8a6a4a, 0.5, new THREE.Vector3(1.2, 0, 0), new THREE.Euler(0, -Math.PI / 2, 0));
  createPanel(0x2a4a5a, 0.4, new THREE.Vector3(0, 0, -1.2), new THREE.Euler(0, 0, 0));
  createPanel(0x1a2838, 0.35, new THREE.Vector3(0, -1.2, 0), new THREE.Euler(Math.PI, 0, 0));
  return scene;
}

function createInfiniteGrid(THREE) {
  const size = 400;
  const vertexShader = `
    varying vec3 vWorldPosition;
    void main() {
      vec4 worldPosition = modelMatrix * vec4(position, 1.0);
      vWorldPosition = worldPosition.xyz;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `;
  const fragmentShader = `
    varying vec3 vWorldPosition;
    uniform float uFadeDistance;
    uniform vec3 uMajorColor;
    uniform vec3 uMinorColor;
    float gridFactor(vec2 coord, float step) {
      vec2 grid = abs(fract(coord / step - 0.5) - 0.5) / fwidth(coord / step);
      return 1.0 - min(min(grid.x, grid.y), 1.0);
    }
    void main() {
      vec2 xz = vWorldPosition.xz;
      float minor = gridFactor(xz, 1.0) * 0.35;
      float major = gridFactor(xz, 5.0) * 0.85;
      float dist = length(vWorldPosition.xz);
      float fade = 1.0 - smoothstep(uFadeDistance * 0.35, uFadeDistance, dist);
      vec3 color = mix(uMinorColor, uMajorColor, major);
      float alpha = max(minor, major) * fade * 0.9;
      if (alpha < 0.02) discard;
      gl_FragColor = vec4(color, alpha);
    }
  `;
  const material = new THREE.ShaderMaterial({
    uniforms: {
      uFadeDistance: { value: 180 },
      uMajorColor: { value: new THREE.Color(0x2eb8b0) },
      uMinorColor: { value: new THREE.Color(0x1a4a52) },
    },
    vertexShader,
    fragmentShader,
    transparent: true,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(size, size), material);
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = -0.02;
  mesh.renderOrder = -2;
  mesh.name = 'si-infinite-grid';
  return mesh;
}

function createGroundContact(THREE) {
  const geometry = new THREE.CircleGeometry(120, 64);
  const material = new THREE.MeshBasicMaterial({
    color: 0x000000,
    transparent: true,
    opacity: 0.22,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = -0.01;
  mesh.renderOrder = -1;
  mesh.name = 'si-ground-contact';
  return mesh;
}

const MEMBER_PBR = {
  steel: { roughness: 0.32, metalness: 0.72, envMapIntensity: 1.1 },
  concrete: { roughness: 0.88, metalness: 0.04, envMapIntensity: 0.85 },
  composite: { roughness: 0.52, metalness: 0.42, envMapIntensity: 0.95 },
  timber: { roughness: 0.78, metalness: 0.0, envMapIntensity: 0.7 },
  wall: { roughness: 0.9, metalness: 0.02, envMapIntensity: 0.8 },
  slab: { roughness: 0.86, metalness: 0.03, envMapIntensity: 0.8 },
  default: { roughness: 0.48, metalness: 0.35, envMapIntensity: 1.0 },
};

export function resolveMemberPbrPreset(element = {}) {
  const type = String(element?.type || element?.element_type || '').toLowerCase();
  const mat = String(element?.material_type || element?.mat || 'steel').toLowerCase();
  if (type.includes('wall')) return MEMBER_PBR.wall;
  if (type.includes('slab') || type.includes('floor')) return MEMBER_PBR.slab;
  return MEMBER_PBR[mat] || MEMBER_PBR.default;
}

export function applyEnvironmentMapToMaterial(material, envMap, element = {}) {
  if (!material || !envMap) return;
  if (!material.isMeshStandardMaterial && !material.isMeshPhysicalMaterial) return;
  const preset = resolveMemberPbrPreset(element);
  material.envMap = envMap;
  material.envMapIntensity = preset.envMapIntensity;
  material.roughness = preset.roughness;
  material.metalness = preset.metalness;
  material.needsUpdate = true;
}

export function applyEnvironmentMapToObject(root, envMap) {
  if (!root || !envMap) return;
  root.traverse((child) => {
    if (!child.isMesh || !child.material) return;
    const mats = Array.isArray(child.material) ? child.material : [child.material];
    mats.forEach((mat) => applyEnvironmentMapToMaterial(mat, envMap, child.userData));
  });
}

export function createViewerVisualScene(THREE, options = {}) {
  const {
    renderer,
    scene,
    camera,
    orthographicCamera,
    controls,
    viewportEl,
    getActiveCamera = () => camera,
    getUseOrthographic = () => false,
    requestRender = () => {},
  } = options;

  const state = {
    quality: 'high',
    technicalDrawing: false,
    technicalEdgeActive: false,
    envMap: null,
    pmrem: null,
    infiniteGrid: null,
    groundContact: null,
    legacyGrid: [],
    outlineGroup: new THREE.Group(),
    outlineMeshes: [],
    technicalEdgeGroup: new THREE.Group(),
    viewCubeEl: null,
    savedBackground: null,
    savedFog: null,
    cameraAnimating: false,
    savedExposure: 1.2,
  };

  state.outlineGroup.name = 'si-selection-outline';
  state.technicalEdgeGroup.name = 'si-technical-edges';
  scene.add(state.outlineGroup);
  scene.add(state.technicalEdgeGroup);

  function setupEnvironment() {
    if (!renderer) return null;
    state.pmrem = new THREE.PMREMGenerator(renderer);
    state.pmrem.compileEquirectangularShader();
    const envScene = createRoomEnvironmentScene(THREE);
    const envTexture = state.pmrem.fromScene(envScene, 0.04).texture;
    envScene.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) o.material.dispose();
    });
    sharedEnvironmentMap = envTexture;
    state.envMap = envTexture;
    scene.environment = envTexture;
    scene.background = new THREE.Color(0x060b12);
    state.savedBackground = scene.background.clone();
    return envTexture;
  }

  function setupGridAndGround() {
    scene.children
      .filter((c) => c.isGridHelper)
      .forEach((grid) => {
        state.legacyGrid.push(grid);
        grid.visible = false;
      });
    state.infiniteGrid = createInfiniteGrid(THREE);
    state.groundContact = createGroundContact(THREE);
    scene.add(state.infiniteGrid);
    scene.add(state.groundContact);
  }

  function setupViewCube() {
    if (!viewportEl || state.viewCubeEl) return;
    const wrap = document.createElement('div');
    wrap.className = 'viewport-viewcube';
    wrap.setAttribute('aria-label', 'Standard views');
    const views = [
      { label: 'ISO', axes: 'iso' },
      { label: 'TOP', axes: 'top' },
      { label: 'FR', axes: 'front' },
      { label: 'RT', axes: 'right' },
    ];
    wrap.innerHTML = `
      <div class="viewport-viewcube__cube" aria-hidden="true">
        <span class="viewport-viewcube__face viewport-viewcube__face--top">Z</span>
        <span class="viewport-viewcube__face viewport-viewcube__face--front">Y</span>
        <span class="viewport-viewcube__face viewport-viewcube__face--right">X</span>
      </div>
      <div class="viewport-viewcube__actions">
        ${views.map((v) => `<button type="button" class="viewport-viewcube__btn" data-view-axes="${v.axes}">${v.label}</button>`).join('')}
      </div>
    `;
    viewportEl.appendChild(wrap);
    state.viewCubeEl = wrap;
    wrap.querySelectorAll('[data-view-axes]').forEach((btn) => {
      btn.addEventListener('click', () => snapToView(btn.getAttribute('data-view-axes')));
    });
  }

  function snapToView(axes) {
    const target = controls?.target?.clone?.() || new THREE.Vector3(24, 14, 14);
    const dist = Math.max(camera.position.distanceTo(target), 40);
    const positions = {
      iso: new THREE.Vector3(dist * 0.85, dist * 0.65, dist * 0.85),
      top: new THREE.Vector3(0, dist, 0.001),
      front: new THREE.Vector3(0, target.y, dist),
      right: new THREE.Vector3(dist, target.y, 0),
    };
    const offset = positions[axes] || positions.iso;
    const fromPos = camera.position.clone();
    const toPos = target.clone().add(offset);
    const duration = 420;
    const start = performance.now();
    state.cameraAnimating = true;
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3;
      camera.position.lerpVectors(fromPos, toPos, eased);
      if (orthographicCamera) {
        orthographicCamera.position.copy(camera.position);
        orthographicCamera.lookAt(target);
      }
      controls?.target?.copy?.(target);
      controls?.update?.();
      requestRender();
      if (t < 1) requestAnimationFrame(step);
      else state.cameraAnimating = false;
    };
    requestAnimationFrame(step);
  }

  function setQuality(level) {
    state.quality = level === 'low' || level === 'medium' ? level : 'high';
    const enableOutline = state.quality !== 'low';
    state.outlineGroup.visible = enableOutline;
    if (renderer) {
      renderer.setPixelRatio(
        state.quality === 'low'
          ? 1
          : Math.min(window.devicePixelRatio || 1, state.quality === 'medium' ? 1.25 : 2),
      );
      const base = state.savedExposure || 1.2;
      renderer.toneMappingExposure = state.quality === 'high' ? base * 1.06 : base;
    }
    requestRender();
  }

  function clearTechnicalEdges() {
    while (state.technicalEdgeGroup.children.length) {
      const child = state.technicalEdgeGroup.children[0];
      state.technicalEdgeGroup.remove(child);
      child.geometry?.dispose?.();
      child.material?.dispose?.();
    }
  }

  function rebuildTechnicalEdges(root) {
    clearTechnicalEdges();
    const useOrtho = getUseOrthographic();
    const active = state.technicalDrawing && useOrtho;
    state.technicalEdgeActive = active;
    const vp = renderer?.domElement?.parentElement;
    if (vp) {
      vp.toggleAttribute('data-viewport-technical-ortho', active);
    }
    if (!active || !root) return;
    root.traverse((child) => {
      if (!child.isMesh || child.userData?._wireframe || child.userData?._instancedGroup) return;
      if (!child.geometry || child.visible === false) return;
      const edges = new THREE.EdgesGeometry(child.geometry, 18);
      const line = new THREE.LineSegments(
        edges,
        new THREE.LineBasicMaterial({ color: 0x1c2430, transparent: true, opacity: 0.92 }),
      );
      line.matrix.copy(child.matrixWorld);
      line.matrixAutoUpdate = false;
      line.renderOrder = 999;
      state.technicalEdgeGroup.add(line);
    });
  }

  function setTechnicalDrawingMode(enabled) {
    state.technicalDrawing = Boolean(enabled);
    if (state.technicalDrawing) {
      state.savedFog = scene.fog;
      scene.fog = null;
      scene.background = new THREE.Color(0xf8f6f2);
      if (state.infiniteGrid?.material?.uniforms) {
        state.infiniteGrid.material.uniforms.uMajorColor.value.set(0x333333);
        state.infiniteGrid.material.uniforms.uMinorColor.value.set(0x666666);
        state.infiniteGrid.material.uniforms.uFadeDistance.value = 220;
      }
      renderer?.domElement?.parentElement?.setAttribute('data-viewport-technical', 'true');
      if (renderer) {
        state.savedExposure = renderer.toneMappingExposure;
        renderer.toneMappingExposure = 1.0;
      }
    } else {
      scene.fog = state.savedFog;
      scene.background = state.savedBackground || new THREE.Color(0x060b12);
      if (state.infiniteGrid?.material?.uniforms) {
        state.infiniteGrid.material.uniforms.uMajorColor.value.set(0x2eb8b0);
        state.infiniteGrid.material.uniforms.uMinorColor.value.set(0x1a4a52);
      }
      renderer?.domElement?.parentElement?.removeAttribute('data-viewport-technical');
      renderer?.domElement?.parentElement?.removeAttribute('data-viewport-technical-ortho');
      if (renderer) renderer.toneMappingExposure = state.savedExposure || 1.2;
      clearTechnicalEdges();
      state.technicalEdgeActive = false;
    }
    requestRender();
  }

  function clearSelectionOutline() {
    while (state.outlineGroup.children.length) {
      const child = state.outlineGroup.children[0];
      state.outlineGroup.remove(child);
      child.geometry?.dispose?.();
      child.material?.dispose?.();
    }
    state.outlineMeshes = [];
  }

  function updateSelectionOutline(selectedMeshes = []) {
    clearSelectionOutline();
    if (state.quality === 'low' || state.technicalDrawing) return;
    const meshes = Array.isArray(selectedMeshes) ? selectedMeshes : selectedMeshes ? [selectedMeshes] : [];
    meshes.forEach((mesh) => {
      if (!mesh?.isMesh || !mesh.geometry) return;
      const outlineMat = new THREE.MeshBasicMaterial({
        color: 0x4fd4cb,
        side: THREE.BackSide,
        transparent: true,
        opacity: 0.55,
        depthTest: true,
      });
      const outline = new THREE.Mesh(mesh.geometry, outlineMat);
      outline.position.copy(mesh.position);
      outline.quaternion.copy(mesh.quaternion);
      outline.scale.copy(mesh.scale).multiplyScalar(1.04);
      outline.renderOrder = mesh.renderOrder + 1;
      state.outlineGroup.add(outline);
      state.outlineMeshes.push(outline);

      const glowMat = new THREE.MeshBasicMaterial({
        color: 0x2eb8b0,
        side: THREE.BackSide,
        transparent: true,
        opacity: 0.18,
        depthTest: true,
      });
      const glow = new THREE.Mesh(mesh.geometry, glowMat);
      glow.position.copy(mesh.position);
      glow.quaternion.copy(mesh.quaternion);
      glow.scale.copy(mesh.scale).multiplyScalar(1.08);
      glow.renderOrder = mesh.renderOrder;
      state.outlineGroup.add(glow);
    });
    requestRender();
  }

  function renderFrame() {
    const useOrtho = getUseOrthographic();
    const activeCamera = useOrtho && orthographicCamera ? orthographicCamera : getActiveCamera();
    if (renderer && scene && activeCamera) {
      renderer.render(scene, activeCamera);
    }
  }

  function onResize(width, height) {
    if (state.infiniteGrid?.material?.uniforms?.uFadeDistance) {
      const span = Math.max(width, height) * 0.35;
      state.infiniteGrid.material.uniforms.uFadeDistance.value = Math.max(120, span);
    }
    requestRender();
  }

  function dispose() {
    clearSelectionOutline();
    clearTechnicalEdges();
    if (state.pmrem) state.pmrem.dispose();
    if (state.envMap) state.envMap.dispose?.();
    sharedEnvironmentMap = null;
    state.viewCubeEl?.remove?.();
  }

  if (renderer) state.savedExposure = renderer.toneMappingExposure;

  setupEnvironment();
  setupGridAndGround();
  setupViewCube();

  return {
    state,
    setupEnvironment,
    setQuality,
    setTechnicalDrawingMode,
    rebuildTechnicalEdges,
    updateSelectionOutline,
    clearSelectionOutline,
    applyEnvironmentToModel: (root) => applyEnvironmentMapToObject(root, state.envMap),
    snapToView,
    renderFrame,
    onResize,
    dispose,
    get environmentMap() {
      return state.envMap;
    },
  };
}
