/**
 * terrain.js — Procedural terrain height and grid generation.
 *
 * Direct port of _terrain_hash, terrain_height, make_terrain_grid,
 * and chunk_has_mountain from run.py.
 */

import { Vec3 } from './math.js';

// ── Terrain hash — pseudo-random height from grid coordinates ───────────

function terrainHash(ix, iz, seed) {
    // Use Math.imul for 32-bit integer multiplication (avoids 2^53 precision loss)
    let h = (Math.imul(seed, 1103515245) + 12345) >>> 0;
    h = (h ^ (Math.imul(ix, 73856093) >>> 0)) >>> 0;
    h = ((Math.imul(h, 1103515245) + 12345) ^ (Math.imul(iz, 19349663) >>> 0)) >>> 0;
    return (h & 0xFFFF) / 0xFFFF;
}


// ── Terrain height at world position ────────────────────────────────────

export function terrainHeight(wx, wz, seed, scale = 8.0, amplitude = 2.5) {
    let total = 0.0;

    // Two octaves of smoothed value noise
    const octaves = [
        [scale, amplitude],
        [scale * 0.4, amplitude * 0.25],
    ];
    for (const [octScale, octAmp] of octaves) {
        const gx = wx / octScale;
        const gz = wz / octScale;
        const ix = Math.floor(gx);
        const iz = Math.floor(gz);
        let fx = gx - ix;
        let fz = gz - iz;
        // Smoothstep
        fx = fx * fx * (3.0 - 2.0 * fx);
        fz = fz * fz * (3.0 - 2.0 * fz);
        // Bilinear interpolation
        const h00 = terrainHash(ix, iz, seed);
        const h10 = terrainHash(ix + 1, iz, seed);
        const h01 = terrainHash(ix, iz + 1, seed);
        const h11 = terrainHash(ix + 1, iz + 1, seed);
        const h0 = h00 + (h10 - h00) * fx;
        const h1 = h01 + (h11 - h01) * fx;
        total += (h0 + (h1 - h0) * fz) * octAmp;
    }

    // Mountain layer
    const mtnScale = 70.0;
    const mtnAmp = 25.0;
    const mtnSeed = seed ^ 0xDEADBEEF;
    {
        const gx = wx / mtnScale;
        const gz = wz / mtnScale;
        const ix = Math.floor(gx);
        const iz = Math.floor(gz);
        let fx = gx - ix;
        let fz = gz - iz;
        fx = fx * fx * (3.0 - 2.0 * fx);
        fz = fz * fz * (3.0 - 2.0 * fz);
        const h00 = terrainHash(ix, iz, mtnSeed);
        const h10 = terrainHash(ix + 1, iz, mtnSeed);
        const h01 = terrainHash(ix, iz + 1, mtnSeed);
        const h11 = terrainHash(ix + 1, iz + 1, mtnSeed);
        const h0 = h00 + (h10 - h00) * fx;
        const h1 = h01 + (h11 - h01) * fx;
        const mtnNoise = h0 + (h1 - h0) * fz;
        const mtnFactor = Math.max(0.0, (mtnNoise - 0.65) / 0.35);
        total += mtnFactor * mtnFactor * mtnFactor * mtnAmp;
    }

    // Guaranteed landmark mountain near spawn
    const mtnCx = 6.0, mtnCz = 45.0;
    const mtnRadius = 18.0;
    const mtnPeak = 30.0;
    const dmx = wx - mtnCx;
    const dmz = wz - mtnCz;
    const d2 = dmx * dmx + dmz * dmz;
    const cutoff = mtnRadius * 3.0;
    if (d2 < cutoff * cutoff) {
        total += mtnPeak * Math.exp(-d2 / (2.0 * mtnRadius * mtnRadius));
    }

    return total - amplitude * 0.3;
}


// ── Check if a chunk contains mountain terrain ─────────────────────────

export function chunkHasMountain(cx, cz, chunkSize, seed, threshold = 0.70) {
    const wx = cx * chunkSize + chunkSize * 0.5;
    const wz = cz * chunkSize + chunkSize * 0.5;

    // Guaranteed landmark
    const mtnCx = 6.0, mtnCz = 45.0;
    const mtnRadius = 18.0;
    const dmx = wx - mtnCx;
    const dmz = wz - mtnCz;
    if (dmx * dmx + dmz * dmz < (mtnRadius * 3.0) ** 2) {
        return true;
    }

    const mtnSeed = seed ^ 0xDEADBEEF;
    const mtnScale = 70.0;
    const gx = wx / mtnScale;
    const gz = wz / mtnScale;
    const ix = Math.floor(gx);
    const iz = Math.floor(gz);
    let fx = gx - ix;
    let fz = gz - iz;
    fx = fx * fx * (3.0 - 2.0 * fx);
    fz = fz * fz * (3.0 - 2.0 * fz);
    const h00 = terrainHash(ix, iz, mtnSeed);
    const h10 = terrainHash(ix + 1, iz, mtnSeed);
    const h01 = terrainHash(ix, iz + 1, mtnSeed);
    const h11 = terrainHash(ix + 1, iz + 1, mtnSeed);
    const h0 = h00 + (h10 - h00) * fx;
    const h1 = h01 + (h11 - h01) * fx;
    const mtnNoise = h0 + (h1 - h0) * fz;
    return mtnNoise > threshold;
}


// ── Terrain grid geometry for a chunk ───────────────────────────────────

/**
 * Generate terrain grid geometry for chunk (cx, cz).
 * Returns { positions, normals, indices, edgeIndices } typed arrays.
 */
export function makeTerrainGrid(cx, cz, chunkSize, seed, gridRes = 6) {
    const cs = chunkSize;
    const cell = cs / gridRes;
    const x0 = cx * cs;
    const z0 = cz * cs;

    // Build vertex grid (gridRes+1 × gridRes+1)
    const grid = [];
    for (let gi = 0; gi <= gridRes; gi++) {
        const row = [];
        for (let gj = 0; gj <= gridRes; gj++) {
            const vx = x0 + gi * cell;
            const vz = z0 + gj * cell;
            const vy = terrainHeight(vx, vz, seed);
            row.push(new Vec3(vx, vy, vz));
        }
        grid.push(row);
    }

    // Generate quads → each quad = 2 triangles for fill + 4 edge lines
    const positions = [];
    const normals = [];
    const indices = [];
    const edgeIndices = [];
    let vertIdx = 0;

    for (let gi = 0; gi < gridRes; gi++) {
        for (let gj = 0; gj < gridRes; gj++) {
            const v00 = grid[gi][gj];
            const v10 = grid[gi + 1][gj];
            const v11 = grid[gi + 1][gj + 1];
            const v01 = grid[gi][gj + 1];

            // Compute face normal: e2 × e1
            const e1 = v10.sub(v00);
            const e2 = v01.sub(v00);
            const normal = new Vec3(
                e2.y * e1.z - e2.z * e1.y,
                e2.z * e1.x - e2.x * e1.z,
                e2.x * e1.y - e2.y * e1.x,
            ).normalize();

            const base = vertIdx;
            for (const v of [v00, v10, v11, v01]) {
                positions.push(v.x, v.y, v.z);
                normals.push(normal.x, normal.y, normal.z);
                vertIdx++;
            }

            // Two triangles
            indices.push(base, base + 1, base + 2);
            indices.push(base, base + 2, base + 3);

            // Edge lines (quad outline)
            edgeIndices.push(base, base + 1);
            edgeIndices.push(base + 1, base + 2);
            edgeIndices.push(base + 2, base + 3);
            edgeIndices.push(base + 3, base);
        }
    }

    return {
        positions: new Float32Array(positions),
        normals: new Float32Array(normals),
        indices: new Uint16Array(indices),
        edgeIndices: new Uint16Array(edgeIndices),
    };
}
