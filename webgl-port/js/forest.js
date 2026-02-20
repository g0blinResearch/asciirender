/**
 * forest.js — Forest primitives, chunk generation, and world streaming.
 *
 * Port of make_pine_tree, make_rock, make_bush, ForestChunk, ForestWorld
 * from run.py.
 */

import { Vec3 } from './math.js';
import { terrainHeight, chunkHasMountain, makeTerrainGrid } from './terrain.js';

// ── Seeded RNG (matching Python random.Random for forest generation) ────

class SeededRNG {
    constructor(seed) {
        this._s = seed >>> 0;
    }

    /** Returns a float in [0, 1). */
    random() {
        // Use Math.imul for 32-bit multiplication (avoids 2^53 precision loss)
        this._s = (Math.imul(this._s, 1103515245) + 12345) & 0x7FFFFFFF;
        return this._s / 0x7FFFFFFF;
    }
}


// ── Helper: rotate around Y axis ────────────────────────────────────────

function rotateY(lx, lz, cosA, sinA) {
    return [lx * cosA + lz * sinA, -lx * sinA + lz * cosA];
}


// ── Geometry builder helper ─────────────────────────────────────────────

/**
 * Append geometry for a single face (triangle or quad) to the accumulator arrays.
 * Computes flat normal from e2 × e1.
 */
function pushFace(acc, verts) {
    const n = verts.length;
    const e1 = verts[1].sub(verts[0]);
    const e2 = verts[n - 1].sub(verts[0]);
    const normal = new Vec3(
        e2.y * e1.z - e2.z * e1.y,
        e2.z * e1.x - e2.x * e1.z,
        e2.x * e1.y - e2.y * e1.x,
    ).normalize();

    const base = acc.vertCount;
    for (const v of verts) {
        acc.positions.push(v.x, v.y, v.z);
        acc.normals.push(normal.x, normal.y, normal.z);
        acc.vertCount++;
    }

    // Triangulate (fan)
    for (let i = 1; i < n - 1; i++) {
        acc.indices.push(base, base + i, base + i + 1);
    }

    // Edge lines
    for (let i = 0; i < n; i++) {
        acc.edgeIndices.push(base + i, base + (i + 1) % n);
    }
}

function createAccumulator() {
    return { positions: [], normals: [], indices: [], edgeIndices: [], vertCount: 0 };
}

function finalizeAccumulator(acc) {
    return {
        positions: new Float32Array(acc.positions),
        normals: new Float32Array(acc.normals),
        indices: new Uint16Array(acc.indices),
        edgeIndices: new Uint16Array(acc.edgeIndices),
    };
}


// ── Pine tree ───────────────────────────────────────────────────────────

function makePineTree(acc, wx, wz, height, angle, rng, baseY = 0.0) {
    const ca = Math.cos(angle), sa = Math.sin(angle);

    // Trunk
    const tw = 0.10;
    const th = height * 0.40;
    const trunkVerts = [];
    for (const [lx, lz] of [[-tw, -tw], [tw, -tw], [tw, tw], [-tw, tw]]) {
        const [rx, rz] = rotateY(lx, lz, ca, sa);
        trunkVerts.push([
            new Vec3(wx + rx, baseY, wz + rz),
            new Vec3(wx + rx, baseY + th, wz + rz),
        ]);
    }
    for (let i = 0; i < 4; i++) {
        const j = (i + 1) % 4;
        const [b0, t0] = trunkVerts[i];
        const [b1, t1] = trunkVerts[j];
        pushFace(acc, [b0, b1, t1, t0]);
    }

    // 3 stacked canopy tiers
    const canopyStart = th * 0.70;
    const canopyHeight = height - canopyStart;
    const tierCount = 3;
    const tierH = canopyHeight / tierCount;

    for (let t = 0; t < tierCount; t++) {
        const tierBaseY = canopyStart + t * tierH * 0.65;
        const tierApexY = canopyStart + (t + 1) * tierH + t * tierH * 0.05;
        const progress = t / tierCount;
        const tierRadius = height * (0.38 - 0.10 * progress);

        const apex = new Vec3(wx, baseY + tierApexY, wz);
        const tierBase = [];
        for (const [lx, lz] of [[-tierRadius, -tierRadius], [tierRadius, -tierRadius],
                                  [tierRadius, tierRadius], [-tierRadius, tierRadius]]) {
            const [rx, rz] = rotateY(lx, lz, ca, sa);
            tierBase.push(new Vec3(wx + rx, baseY + tierBaseY, wz + rz));
        }

        for (let i = 0; i < 4; i++) {
            const j = (i + 1) % 4;
            pushFace(acc, [tierBase[i], tierBase[j], apex]);
        }
    }
}


// ── Rock ────────────────────────────────────────────────────────────────

function makeRock(acc, wx, wz, scale, angle, rng, baseY = 0.0) {
    const ca = Math.cos(angle), sa = Math.sin(angle);
    const rh = scale * (0.3 + rng.random() * 0.3);
    const rw = scale * 0.5;
    const offx = scale * (rng.random() - 0.5) * 0.3;
    const offz = scale * (rng.random() - 0.5) * 0.3;

    const ptsLocal = [
        [-rw, baseY, -rw * 0.7],
        [rw, baseY, -rw * 0.5],
        [rw * 0.3, baseY, rw],
        [offx, baseY + rh, offz],
    ];

    const pts = ptsLocal.map(([lx, ly, lz]) => {
        const [rx, rz] = rotateY(lx, lz, ca, sa);
        return new Vec3(wx + rx, ly, wz + rz);
    });

    pushFace(acc, [pts[0], pts[1], pts[3]]);
    pushFace(acc, [pts[1], pts[2], pts[3]]);
    pushFace(acc, [pts[2], pts[0], pts[3]]);
    pushFace(acc, [pts[0], pts[2], pts[1]]);  // bottom
}


// ── Bush ────────────────────────────────────────────────────────────────

function makeBush(acc, wx, wz, scale, angle, rng, baseY = 0.0) {
    const ca = Math.cos(angle), sa = Math.sin(angle);
    const bw = scale * 0.4;
    const bh = scale * 0.35;
    const apex = new Vec3(wx, baseY + bh, wz);

    const base = [];
    for (const [lx, lz] of [[-bw, -bw], [bw, -bw], [bw, bw], [-bw, bw]]) {
        const [rx, rz] = rotateY(lx, lz, ca, sa);
        base.push(new Vec3(wx + rx, baseY, wz + rz));
    }

    for (let i = 0; i < 4; i++) {
        const j = (i + 1) % 4;
        pushFace(acc, [base[i], base[j], apex]);
    }
}


// ── ForestChunk ─────────────────────────────────────────────────────────

const CELL_GRID = 4;
const OBJ_WEIGHTS = [
    ['tree',  0.30],
    ['rock',  0.20],
    ['bush',  0.25],
    ['empty', 0.25],
];

function chunkSeed(worldSeed, cx, cz) {
    let h = worldSeed >>> 0;
    h = ((Math.imul(h, 1103515245) + 12345) ^ (Math.imul(cx, 73856093) >>> 0)) >>> 0;
    h = ((Math.imul(h, 1103515245) + 12345) ^ (Math.imul(cz, 19349663) >>> 0)) >>> 0;
    return h;
}

export class ForestChunk {
    constructor(cx, cz, chunkSize, worldSeed, terrainOnly = false) {
        this.cx = cx;
        this.cz = cz;
        this.chunkSize = chunkSize;
        this.terrainOnly = terrainOnly;

        // Geometry data — filled by _generate
        this.objectGeo = null;    // { positions, normals, indices, edgeIndices }
        this.terrainGeo = null;   // { positions, normals, indices, edgeIndices }

        // WebGL buffer handles (set by renderer)
        this.glBuffers = null;

        this._generate(worldSeed);
    }

    _generate(worldSeed) {
        const cs = this.chunkSize;

        // Terrain grid (always)
        const gridRes = this.terrainOnly ? 3 : 6;
        this.terrainGeo = makeTerrainGrid(this.cx, this.cz, cs, worldSeed, gridRes);

        if (this.terrainOnly) return;

        // Object placement
        const rng = new SeededRNG(chunkSeed(worldSeed, this.cx, this.cz));
        const cellSize = cs / CELL_GRID;
        const acc = createAccumulator();

        for (let gi = 0; gi < CELL_GRID; gi++) {
            for (let gj = 0; gj < CELL_GRID; gj++) {
                const cellCx = this.cx * cs + (gi + 0.5) * cellSize;
                const cellCz = this.cz * cs + (gj + 0.5) * cellSize;

                // Weighted random object type
                const roll = rng.random();
                let cumulative = 0;
                let objType = 'empty';
                for (const [otype, weight] of OBJ_WEIGHTS) {
                    cumulative += weight;
                    if (roll < cumulative) {
                        objType = otype;
                        break;
                    }
                }

                if (objType === 'empty') continue;

                // Jitter position
                const jx = (rng.random() - 0.5) * cellSize * 0.7;
                const jz = (rng.random() - 0.5) * cellSize * 0.7;
                const wx = cellCx + jx;
                const wz = cellCz + jz;
                const angle = rng.random() * Math.PI * 2;
                const by = terrainHeight(wx, wz, worldSeed);

                if (objType === 'tree') {
                    const height = 1.8 + rng.random() * 1.5;
                    makePineTree(acc, wx, wz, height, angle, rng, by);
                } else if (objType === 'rock') {
                    const scale = 0.25 + rng.random() * 0.4;
                    makeRock(acc, wx, wz, scale, angle, rng, by);
                } else if (objType === 'bush') {
                    const scale = 0.4 + rng.random() * 0.3;
                    makeBush(acc, wx, wz, scale, angle, rng, by);
                }
            }
        }

        if (acc.vertCount > 0) {
            this.objectGeo = finalizeAccumulator(acc);
        }
    }
}


// ── ForestWorld ─────────────────────────────────────────────────────────

export class ForestWorld {
    constructor(seed = 42, chunkSize = 12.0, renderDistance = 2) {
        this.seed = seed;
        this.chunkSize = chunkSize;
        this.renderDistance = renderDistance;
        /** @type {Map<string, ForestChunk>} */
        this.chunks = new Map();
        this._mtnCache = new Map();
        this.lastFaceCount = 0;
        this.lastMtnChunks = 0;
    }

    /** Key for chunk map. */
    _key(cx, cz) {
        return `${cx},${cz}`;
    }

    /**
     * Load/unload chunks based on camera position.
     * Returns arrays of newly loaded and unloaded chunk keys.
     */
    update(cameraPosition) {
        const cs = this.chunkSize;
        const camCx = Math.floor(cameraPosition.x / cs);
        const camCz = Math.floor(cameraPosition.z / cs);
        const rd = this.renderDistance;

        // Normal chunks (full detail)
        const needed = new Set();
        for (let dx = -rd; dx <= rd; dx++) {
            for (let dz = -rd; dz <= rd; dz++) {
                needed.add(this._key(camCx + dx, camCz + dz));
            }
        }

        // Extended mountain chunks (terrain-only)
        const mtnRd = Math.max(16, rd * 3);
        const mtnNeeded = new Set();
        for (let dx = -mtnRd; dx <= mtnRd; dx++) {
            for (let dz = -mtnRd; dz <= mtnRd; dz++) {
                const key = this._key(camCx + dx, camCz + dz);
                if (needed.has(key)) continue;
                const cx = camCx + dx, cz = camCz + dz;
                if (!this._mtnCache.has(key)) {
                    this._mtnCache.set(key, chunkHasMountain(cx, cz, cs, this.seed));
                }
                if (this._mtnCache.get(key)) {
                    mtnNeeded.add(key);
                }
            }
        }
        this.lastMtnChunks = mtnNeeded.size;

        const allNeeded = new Set([...needed, ...mtnNeeded]);

        // Unload
        const toRemove = [];
        for (const key of this.chunks.keys()) {
            if (!allNeeded.has(key)) {
                toRemove.push(key);
            }
        }
        for (const key of toRemove) {
            this.chunks.delete(key);
        }

        // Load new chunks (budget per frame)
        const maxLoad = rd <= 3 ? 2 : 4;
        let loaded = 0;

        // Full-detail chunks first
        for (const key of needed) {
            if (!this.chunks.has(key)) {
                const [cx, cz] = key.split(',').map(Number);
                this.chunks.set(key, new ForestChunk(cx, cz, cs, this.seed, false));
                loaded++;
                if (loaded >= maxLoad) break;
            }
        }

        // Mountain chunks (terrain-only, higher budget)
        let mtnLoaded = 0;
        const mtnMax = 8;
        for (const key of mtnNeeded) {
            if (!this.chunks.has(key)) {
                const [cx, cz] = key.split(',').map(Number);
                this.chunks.set(key, new ForestChunk(cx, cz, cs, this.seed, true));
                mtnLoaded++;
                if (mtnLoaded >= mtnMax) break;
            }
        }

        return { removed: toRemove };
    }
}
