/**
 * main.js — Entry point and animation loop.
 *
 * Coordinates all subsystems: renderer, camera, input, models, forest.
 * Supports three modes: spin (auto-rotation), move (free camera), forest.
 */

import { Vec3, Quaternion, mat4 } from './math.js';
import { Camera } from './camera.js';
import { InputManager } from './input.js';
import { MODELS } from './models.js';
import { Renderer } from './renderer.js';
import { ForestWorld } from './forest.js';
import { terrainHeight } from './terrain.js';

// ── Application state ───────────────────────────────────────────────────

let renderer;
let camera;
let input;
let mode = 'spin';            // 'spin' | 'move' | 'forest'
let currentModel = 'cube';
let forestWorld = null;

// Model geometry and buffers
let modelGeo = null;
let modelBuf = null;

// Forest chunk buffers: Map<string, {objectBuf, terrainBuf}>
const chunkBuffers = new Map();

// Spin mode state
let orientation = Quaternion.identity();
let frameCount = 0;
const spinSpeedX = 0.01;
const spinSpeedY = 0.03;
const spinSpeedZ = 0.02;

// Movement speeds
let moveSpeed = 0.15;
let turnSpeed = 0.05;

// Model size
let modelSize = 1.5;

// FOV
let fovDeg = 90;

// Forest settings
let forestSeed = 42;
let baseRenderDist = 2;

// Reusable matrices
const modelMatrix = mat4.create();
const identityMatrix = mat4.create();
mat4.identity(identityMatrix);

// ── Initialise ──────────────────────────────────────────────────────────

function init() {
    const canvas = document.getElementById('glcanvas');
    renderer = new Renderer(canvas);
    input = new InputManager();
    camera = new Camera(new Vec3(0, 0, 5));

    // Read initial settings from URL params
    const params = new URLSearchParams(window.location.search);
    if (params.has('model')) currentModel = params.get('model');
    if (params.has('forest')) {
        mode = 'forest';
    } else if (params.has('move')) {
        mode = 'move';
    }
    if (params.has('seed')) forestSeed = parseInt(params.get('seed')) || 42;
    if (params.has('fov')) fovDeg = parseFloat(params.get('fov')) || 90;
    if (params.has('size')) modelSize = parseFloat(params.get('size')) || 1.5;
    if (params.has('render-dist')) baseRenderDist = parseInt(params.get('render-dist')) || 2;

    // Setup UI controls
    setupUI();

    // Load initial state
    if (mode === 'forest') {
        startForestMode();
    } else {
        loadModel(currentModel);
        if (mode === 'move') {
            setupMoveCamera();
        }
    }

    // Start animation
    renderer.resize();
    requestAnimationFrame(loop);
}

function setupUI() {
    // Model selector buttons
    const modelBtns = document.querySelectorAll('[data-model]');
    modelBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const m = btn.dataset.model;
            if (m === 'forest') {
                startForestMode();
            } else {
                if (mode === 'forest') stopForestMode();
                currentModel = m;
                loadModel(m);
                mode = 'spin';
                orientation = Quaternion.identity();
                camera = new Camera(new Vec3(0, 0, 5));
            }
            updateModeDisplay();
            updateActiveButton(btn);
        });
    });

    // Mode toggle
    document.getElementById('mode-toggle')?.addEventListener('click', () => {
        if (mode === 'forest') return;
        mode = mode === 'spin' ? 'move' : 'spin';
        if (mode === 'move') {
            setupMoveCamera();
        }
        updateModeDisplay();
    });

    updateModeDisplay();
}

function updateActiveButton(activeBtn) {
    document.querySelectorAll('[data-model]').forEach(b => b.classList.remove('active'));
    activeBtn.classList.add('active');
}

function updateModeDisplay() {
    const badge = document.getElementById('mode-badge');
    const controls = document.getElementById('controls-help');
    const modeToggle = document.getElementById('mode-toggle');

    if (mode === 'forest') {
        badge.textContent = 'FOREST';
        badge.className = 'mode-badge forest';
        controls.textContent = 'WASD=move Arrows=turn E/C=pitch R/F=up/dn Q=quit';
        if (modeToggle) modeToggle.style.display = 'none';
    } else if (mode === 'move') {
        badge.textContent = 'MOVE';
        badge.className = 'mode-badge move';
        controls.textContent = 'WASD=move Arrows=turn R/F=up/dn E/C=pitch Tab=spin';
        if (modeToggle) modeToggle.style.display = '';
    } else {
        badge.textContent = 'SPIN';
        badge.className = 'mode-badge spin';
        controls.textContent = 'Tab=move';
        if (modeToggle) modeToggle.style.display = '';
    }
}


// ── Model loading ───────────────────────────────────────────────────────

function loadModel(name) {
    // Delete old buffers
    if (modelBuf) {
        renderer.deleteBuffers(modelBuf);
        modelBuf = null;
    }

    const builder = MODELS[name];
    if (!builder) return;

    modelGeo = builder(modelSize);
    modelBuf = renderer.createBuffers(modelGeo);

    // Set camera distance based on model size
    const maxR = boundingRadius(modelGeo);
    moveSpeed = maxR * 0.06;
    camera = new Camera(new Vec3(0, maxR * 0.3, maxR * 3));

    renderer.lightPos = new Vec3(3, 4, 3);
    renderer.fogDistance = 0;
    renderer.drawEdges = true;
}

function boundingRadius(geo) {
    let maxR = 0;
    for (let i = 0; i < geo.positions.length; i += 3) {
        const x = geo.positions[i], y = geo.positions[i + 1], z = geo.positions[i + 2];
        maxR = Math.max(maxR, Math.sqrt(x * x + y * y + z * z));
    }
    return maxR;
}

function setupMoveCamera() {
    if (modelGeo) {
        const maxR = boundingRadius(modelGeo);
        camera = new Camera(new Vec3(0, maxR * 0.3, maxR * 3));
        moveSpeed = maxR * 0.06;
    }
}


// ── Forest mode ─────────────────────────────────────────────────────────

function startForestMode() {
    mode = 'forest';
    forestWorld = new ForestWorld(forestSeed, 12.0, baseRenderDist);

    camera = new Camera(new Vec3(6, 1.5, 6));
    moveSpeed = 0.15;
    turnSpeed = 0.05;

    renderer.fogDistance = 12.0 * baseRenderDist;
    renderer.fogColor = [0.16, 0.18, 0.23];  // match sky horizon colour
    renderer.drawEdges = true;

    // Delete model buffers if any
    if (modelBuf) {
        renderer.deleteBuffers(modelBuf);
        modelBuf = null;
        modelGeo = null;
    }

    updateModeDisplay();
}

function stopForestMode() {
    if (!forestWorld) return;

    // Delete all chunk buffers
    for (const [key, bufs] of chunkBuffers) {
        if (bufs.objectBuf) renderer.deleteBuffers(bufs.objectBuf);
        if (bufs.terrainBuf) renderer.deleteBuffers(bufs.terrainBuf);
    }
    chunkBuffers.clear();
    forestWorld = null;
}

function updateForestBuffers() {
    if (!forestWorld) return;

    const { removed } = forestWorld.update(camera.position);

    // Delete removed chunk buffers
    for (const key of removed) {
        const bufs = chunkBuffers.get(key);
        if (bufs) {
            if (bufs.objectBuf) renderer.deleteBuffers(bufs.objectBuf);
            if (bufs.terrainBuf) renderer.deleteBuffers(bufs.terrainBuf);
            chunkBuffers.delete(key);
        }
    }

    // Create buffers for new chunks
    for (const [key, chunk] of forestWorld.chunks) {
        if (!chunkBuffers.has(key)) {
            const bufs = {};
            if (chunk.objectGeo) {
                bufs.objectBuf = renderer.createBuffers(chunk.objectGeo);
            }
            if (chunk.terrainGeo) {
                bufs.terrainBuf = renderer.createBuffers(chunk.terrainGeo);
            }
            chunkBuffers.set(key, bufs);
        }
    }
}


// ── Input handling ──────────────────────────────────────────────────────

function handleInput() {
    // One-shot keys
    for (const key of input.justPressed) {
        if (key === 'tab' && mode !== 'forest') {
            mode = mode === 'spin' ? 'move' : 'spin';
            if (mode === 'move') {
                setupMoveCamera();
            }
            updateModeDisplay();
        }
    }
    input.clearFrame();

    // Held keys (movement mode and forest mode)
    if (mode === 'move' || mode === 'forest') {
        if (input.anyHeld('arrowup', 'w')) camera.moveForward(moveSpeed);
        if (input.anyHeld('arrowdown', 's')) camera.moveForward(-moveSpeed);
        if (input.isHeld('arrowleft')) camera.turn(-turnSpeed);
        if (input.isHeld('arrowright')) camera.turn(turnSpeed);
        if (input.anyHeld('a')) camera.moveRight(-moveSpeed);
        if (input.anyHeld('d')) camera.moveRight(moveSpeed);
        if (input.anyHeld('r', ' ')) camera.moveUp(moveSpeed);
        if (input.anyHeld('f')) camera.moveUp(-moveSpeed);
        if (input.anyHeld('e')) camera.turn(0, turnSpeed);
        if (input.anyHeld('c')) camera.turn(0, -turnSpeed);
    }
}


// ── Update ──────────────────────────────────────────────────────────────

function update() {
    handleInput();

    if (mode === 'forest' && forestWorld) {
        // Track terrain height
        const cp = camera.position;
        const ty = terrainHeight(cp.x, cp.z, forestWorld.seed);
        cp.y = ty + 1.5;

        // Dynamic render distance
        const extraRd = Math.min(4, Math.floor(cp.y / 4.0));
        const effectiveRd = baseRenderDist + Math.max(0, extraRd);
        if (effectiveRd !== forestWorld.renderDistance) {
            forestWorld.renderDistance = effectiveRd;
            renderer.fogDistance = 12.0 * effectiveRd;
        }

        // Move light with camera
        renderer.lightPos = new Vec3(cp.x + 5, cp.y + 20, cp.z + 5);

        updateForestBuffers();
    } else if (mode === 'spin') {
        // Quaternion rotation
        if (spinSpeedY) {
            const qy = Quaternion.fromAxisAngle(new Vec3(0, 1, 0), spinSpeedY);
            orientation = qy.multiply(orientation);
        }
        if (spinSpeedX) {
            const qx = Quaternion.fromAxisAngle(new Vec3(1, 0, 0), spinSpeedX);
            orientation = qx.multiply(orientation);
        }
        frameCount++;
        if (frameCount % 60 === 0) orientation.normalize();
    }

    // Update status bar
    updateStatus();
}

function updateStatus() {
    const status = document.getElementById('status-bar');
    if (!status) return;

    if (mode === 'forest' && forestWorld) {
        const nc = forestWorld.chunks.size;
        const mc = forestWorld.lastMtnChunks;
        const px = camera.position.x.toFixed(0);
        const py = camera.position.y.toFixed(1);
        const pz = camera.position.z.toFixed(0);
        status.textContent = `Chunks:${nc}(mtn:${mc}) Pos:(${px},${py},${pz})`;
    } else if (mode === 'move') {
        const px = camera.position.x.toFixed(1);
        const py = camera.position.y.toFixed(1);
        const pz = camera.position.z.toFixed(1);
        status.textContent = `Pos:(${px},${py},${pz})`;
    } else {
        status.textContent = `Frame:${frameCount}`;
    }
}


// ── Render ──────────────────────────────────────────────────────────────

function render() {
    renderer.resize();
    renderer.beginFrame();

    if (mode === 'forest') {
        renderForest();
    } else if (mode === 'move') {
        renderMoveMode();
    } else {
        renderSpinMode();
    }
}

function renderSpinMode() {
    // Orthographic projection
    const maxR = modelGeo ? boundingRadius(modelGeo) : 3;
    renderer.setOrthographic(maxR * 1.2);

    // View matrix: identity (camera at origin looking down -Z)
    // Uses cached identityMatrix to avoid per-frame allocation

    // Model matrix from quaternion orientation
    orientation.toMat4(modelMatrix);

    renderer.lightPos = new Vec3(3, 4, 3);
    renderer.fogDistance = 0;

    if (modelBuf) {
        renderer.drawModel(modelBuf, identityMatrix, modelMatrix);
    }
}

function renderMoveMode() {
    renderer.setPerspective(fovDeg);
    const viewMatrix = camera.getViewMatrix();

    renderer.drawSky(camera.pitch);

    mat4.identity(modelMatrix);
    renderer.fogDistance = 0;

    if (modelBuf) {
        renderer.drawModel(modelBuf, viewMatrix, modelMatrix);
    }
}

function renderForest() {
    renderer.setPerspective(fovDeg);
    const viewMatrix = camera.getViewMatrix();

    renderer.drawSky(camera.pitch);

    mat4.identity(modelMatrix);

    // Draw all chunk geometry
    for (const [key, bufs] of chunkBuffers) {
        // Draw terrain
        if (bufs.terrainBuf) {
            renderer.drawTerrainWireframe(bufs.terrainBuf, viewMatrix, modelMatrix);
        }
        // Draw objects (trees, rocks, bushes)
        if (bufs.objectBuf) {
            renderer.drawModel(bufs.objectBuf, viewMatrix, modelMatrix);
        }
    }
}


// ── Animation loop ──────────────────────────────────────────────────────

function loop() {
    update();
    render();
    requestAnimationFrame(loop);
}


// ── Kick off ────────────────────────────────────────────────────────────

window.addEventListener('DOMContentLoaded', init);
