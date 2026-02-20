/**
 * models.js — Cube, Car, HouseScene geometry builders.
 *
 * Each function returns { positions, normals, indices, edgeIndices }
 * where positions/normals are Float32Array and indices are Uint16Array.
 *
 * Faces are triangulated (quads → 2 triangles). Vertices are duplicated
 * per-face so each face gets its own flat normal — matching the original
 * Python renderer's flat-shading style.
 */

import { Vec3 } from './math.js';

// ── Helper: build geometry from vertex list + face index tuples ─────────

/**
 * Convert a list of Vec3 vertices and face index tuples into flat
 * Float32Array/Uint16Array buffers for WebGL.
 *
 * Each face gets duplicated vertices with the face normal assigned to each
 * vertex — this produces flat shading without needing GLSL `flat` qualifier.
 */
function buildGeometry(vertices, faces) {
    const positions = [];
    const normals = [];
    const indices = [];
    const edgeIndices = [];
    let vertIdx = 0;

    for (const face of faces) {
        const vs = face.map(i => vertices[i]);
        const n = vs.length;

        // Compute face normal: e2 × e1 (matching run.py convention)
        const e1 = vs[1].sub(vs[0]);
        const e2 = vs[n - 1].sub(vs[0]);
        const normal = new Vec3(
            e2.y * e1.z - e2.z * e1.y,
            e2.z * e1.x - e2.x * e1.z,
            e2.x * e1.y - e2.y * e1.x,
        ).normalize();

        // Add vertices with duplicated normals
        const baseIdx = vertIdx;
        for (const v of vs) {
            positions.push(v.x, v.y, v.z);
            normals.push(normal.x, normal.y, normal.z);
            vertIdx++;
        }

        // Triangulate (fan from first vertex)
        for (let i = 1; i < n - 1; i++) {
            indices.push(baseIdx, baseIdx + i, baseIdx + i + 1);
        }

        // Edge indices (line loop)
        for (let i = 0; i < n; i++) {
            edgeIndices.push(baseIdx + i, baseIdx + (i + 1) % n);
        }
    }

    return {
        positions: new Float32Array(positions),
        normals: new Float32Array(normals),
        indices: new Uint16Array(indices),
        edgeIndices: new Uint16Array(edgeIndices),
    };
}


// ── Cube ────────────────────────────────────────────────────────────────

export function buildCubeGeometry(size = 1.5) {
    const s = size;
    const vertices = [
        new Vec3(-s, -s, -s), new Vec3(s, -s, -s), new Vec3(s, s, -s), new Vec3(-s, s, -s),
        new Vec3(-s, -s,  s), new Vec3(s, -s,  s), new Vec3(s, s,  s), new Vec3(-s, s,  s),
    ];
    const faces = [
        [0, 1, 2, 3],   // back   (−z)
        [5, 4, 7, 6],   // front  (+z)
        [4, 0, 3, 7],   // left   (−x)
        [1, 5, 6, 2],   // right  (+x)
        [3, 2, 6, 7],   // top    (+y)
        [4, 5, 1, 0],   // bottom (−y)
    ];
    return buildGeometry(vertices, faces);
}


// ── Car ─────────────────────────────────────────────────────────────────

export function buildCarGeometry(size = 1.0) {
    const s = size;
    const vertices = [
        // Body bottom (y = −0.5)
        new Vec3(-0.80 * s, -0.50 * s,  2.00 * s),   //  0
        new Vec3( 0.80 * s, -0.50 * s,  2.00 * s),   //  1
        new Vec3( 0.80 * s, -0.50 * s, -2.00 * s),   //  2
        new Vec3(-0.80 * s, -0.50 * s, -2.00 * s),   //  3

        // Belt line (y = 0.0)
        new Vec3(-0.80 * s,  0.00 * s,  2.00 * s),   //  4
        new Vec3( 0.80 * s,  0.00 * s,  2.00 * s),   //  5
        new Vec3( 0.80 * s,  0.00 * s, -2.00 * s),   //  6
        new Vec3(-0.80 * s,  0.00 * s, -2.00 * s),   //  7

        // Windshield base (y = 0.0, z = 0.7)
        new Vec3(-0.80 * s,  0.00 * s,  0.70 * s),   //  8
        new Vec3( 0.80 * s,  0.00 * s,  0.70 * s),   //  9

        // Rear-window base (y = 0.0, z = −1.0)
        new Vec3( 0.80 * s,  0.00 * s, -1.00 * s),   // 10
        new Vec3(-0.80 * s,  0.00 * s, -1.00 * s),   // 11

        // Roof
        new Vec3(-0.72 * s,  0.65 * s,  0.35 * s),   // 12
        new Vec3( 0.72 * s,  0.65 * s,  0.35 * s),   // 13
        new Vec3( 0.72 * s,  0.65 * s, -0.65 * s),   // 14
        new Vec3(-0.72 * s,  0.65 * s, -0.65 * s),   // 15
    ];

    const faces = [
        [0, 1, 2, 3],       // bottom
        [0, 4, 5, 1],       // front bumper
        [2, 6, 7, 3],       // rear bumper
        [1, 5, 6, 2],       // right body side
        [3, 7, 4, 0],       // left body side
        [8, 9, 5, 4],       // hood
        [10, 11, 7, 6],     // trunk
        [8, 12, 13, 9],     // windshield
        [10, 14, 15, 11],   // rear window
        [13, 12, 15, 14],   // roof
        [9, 13, 14, 10],    // right cabin
        [11, 15, 12, 8],    // left cabin
    ];
    return buildGeometry(vertices, faces);
}


// ── HouseScene ──────────────────────────────────────────────────────────

export function buildHouseGeometry(size = 1.0) {
    const s = size;
    const vertices = [
        // Ground (0–3)
        new Vec3(-2.30 * s, -0.02 * s, -1.80 * s),
        new Vec3( 2.30 * s, -0.02 * s, -1.80 * s),
        new Vec3( 2.30 * s, -0.02 * s,  1.80 * s),
        new Vec3(-2.30 * s, -0.02 * s,  1.80 * s),

        // House body (4–11)
        new Vec3(-1.00 * s,  0.00 * s, -0.75 * s),
        new Vec3( 1.00 * s,  0.00 * s, -0.75 * s),
        new Vec3( 1.00 * s,  0.00 * s,  0.75 * s),
        new Vec3(-1.00 * s,  0.00 * s,  0.75 * s),
        new Vec3(-1.00 * s,  1.50 * s, -0.75 * s),
        new Vec3( 1.00 * s,  1.50 * s, -0.75 * s),
        new Vec3( 1.00 * s,  1.50 * s,  0.75 * s),
        new Vec3(-1.00 * s,  1.50 * s,  0.75 * s),

        // Roof eaves + ridge (12–17)
        new Vec3(-1.15 * s,  1.50 * s, -0.85 * s),
        new Vec3( 1.15 * s,  1.50 * s, -0.85 * s),
        new Vec3( 1.15 * s,  1.50 * s,  0.85 * s),
        new Vec3(-1.15 * s,  1.50 * s,  0.85 * s),
        new Vec3( 0.00 * s,  2.30 * s, -0.85 * s),
        new Vec3( 0.00 * s,  2.30 * s,  0.85 * s),

        // Tree 1 — left (18–22)
        new Vec3(-1.95 * s,  0.00 * s, -1.15 * s),
        new Vec3(-1.25 * s,  0.00 * s, -1.15 * s),
        new Vec3(-1.25 * s,  0.00 * s, -0.45 * s),
        new Vec3(-1.95 * s,  0.00 * s, -0.45 * s),
        new Vec3(-1.60 * s,  1.80 * s, -0.80 * s),

        // Tree 2 — right (23–27)
        new Vec3( 1.35 * s,  0.00 * s,  0.35 * s),
        new Vec3( 1.85 * s,  0.00 * s,  0.35 * s),
        new Vec3( 1.85 * s,  0.00 * s,  0.85 * s),
        new Vec3( 1.35 * s,  0.00 * s,  0.85 * s),
        new Vec3( 1.60 * s,  1.20 * s,  0.60 * s),
    ];

    const faces = [
        // Ground
        [0, 1, 2, 3],
        [3, 2, 1, 0],

        // House walls
        [4, 5, 9, 8],
        [6, 7, 11, 10],
        [5, 6, 10, 9],
        [7, 4, 8, 11],

        // Roof
        [12, 16, 17, 15],
        [13, 14, 17, 16],
        [12, 13, 16],       // front gable (triangle)
        [14, 15, 17],       // rear gable  (triangle)

        // Tree 1
        [18, 19, 22],
        [19, 20, 22],
        [20, 21, 22],
        [21, 18, 22],
        [18, 21, 20, 19],

        // Tree 2
        [23, 24, 27],
        [24, 25, 27],
        [25, 26, 27],
        [26, 23, 27],
        [23, 26, 25, 24],
    ];
    return buildGeometry(vertices, faces);
}


// ── Model registry ──────────────────────────────────────────────────────

export const MODELS = {
    cube:  buildCubeGeometry,
    car:   buildCarGeometry,
    house: buildHouseGeometry,
};
