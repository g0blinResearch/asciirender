/**
 * math.js — Vec3, Quaternion, and 4×4 matrix utilities.
 *
 * Direct port of the Vec3 and Quaternion classes from run.py,
 * plus minimal mat4 helpers for WebGL projection/view matrices.
 */

// ── Vec3 ────────────────────────────────────────────────────────────────────

export class Vec3 {
    constructor(x = 0, y = 0, z = 0) {
        this.x = x;
        this.y = y;
        this.z = z;
    }

    dot(other) {
        return this.x * other.x + this.y * other.y + this.z * other.z;
    }

    length() {
        return Math.sqrt(this.x * this.x + this.y * this.y + this.z * this.z);
    }

    normalize() {
        const l = this.length();
        if (l > 0) {
            return new Vec3(this.x / l, this.y / l, this.z / l);
        }
        return new Vec3(0, 0, 0);
    }

    add(other) {
        return new Vec3(this.x + other.x, this.y + other.y, this.z + other.z);
    }

    sub(other) {
        return new Vec3(this.x - other.x, this.y - other.y, this.z - other.z);
    }

    scale(s) {
        return new Vec3(this.x * s, this.y * s, this.z * s);
    }

    cross(other) {
        return new Vec3(
            this.y * other.z - this.z * other.y,
            this.z * other.x - this.x * other.z,
            this.x * other.y - this.y * other.x,
        );
    }

    clone() {
        return new Vec3(this.x, this.y, this.z);
    }
}


// ── Quaternion ──────────────────────────────────────────────────────────────

export class Quaternion {
    constructor(w = 1, x = 0, y = 0, z = 0) {
        this.w = w;
        this.x = x;
        this.y = y;
        this.z = z;
    }

    static fromAxisAngle(axis, angle) {
        const half = angle * 0.5;
        const s = Math.sin(half);
        return new Quaternion(Math.cos(half), axis.x * s, axis.y * s, axis.z * s);
    }

    static identity() {
        return new Quaternion(1, 0, 0, 0);
    }

    multiply(other) {
        return new Quaternion(
            this.w * other.w - this.x * other.x - this.y * other.y - this.z * other.z,
            this.w * other.x + this.x * other.w + this.y * other.z - this.z * other.y,
            this.w * other.y - this.x * other.z + this.y * other.w + this.z * other.x,
            this.w * other.z + this.x * other.y - this.y * other.x + this.z * other.w,
        );
    }

    normalize() {
        const n = Math.sqrt(this.w * this.w + this.x * this.x + this.y * this.y + this.z * this.z);
        if (n > 0) {
            const inv = 1.0 / n;
            this.w *= inv;
            this.x *= inv;
            this.y *= inv;
            this.z *= inv;
        }
        return this;
    }

    rotateVector(v) {
        const { w: qw, x: qx, y: qy, z: qz } = this;
        const tx = 2.0 * (qy * v.z - qz * v.y);
        const ty = 2.0 * (qz * v.x - qx * v.z);
        const tz = 2.0 * (qx * v.y - qy * v.x);
        return new Vec3(
            v.x + qw * tx + (qy * tz - qz * ty),
            v.y + qw * ty + (qz * tx - qx * tz),
            v.z + qw * tz + (qx * ty - qy * tx),
        );
    }

    /** Convert to a 4×4 rotation matrix (column-major for WebGL). */
    toMat4(out) {
        const { w, x, y, z } = this;
        const x2 = x + x, y2 = y + y, z2 = z + z;
        const xx = x * x2, xy = x * y2, xz = x * z2;
        const yy = y * y2, yz = y * z2, zz = z * z2;
        const wx = w * x2, wy = w * y2, wz = w * z2;

        out[0]  = 1 - (yy + zz);
        out[1]  = xy + wz;
        out[2]  = xz - wy;
        out[3]  = 0;
        out[4]  = xy - wz;
        out[5]  = 1 - (xx + zz);
        out[6]  = yz + wx;
        out[7]  = 0;
        out[8]  = xz + wy;
        out[9]  = yz - wx;
        out[10] = 1 - (xx + yy);
        out[11] = 0;
        out[12] = 0;
        out[13] = 0;
        out[14] = 0;
        out[15] = 1;
        return out;
    }
}


// ── Mat4 utilities (column-major, WebGL convention) ─────────────────────────

export const mat4 = {
    create() {
        return new Float32Array(16);
    },

    identity(out) {
        out.fill(0);
        out[0] = out[5] = out[10] = out[15] = 1;
        return out;
    },

    perspective(out, fovYRad, aspect, near, far) {
        const f = 1.0 / Math.tan(fovYRad / 2);
        const nf = 1.0 / (near - far);
        out.fill(0);
        out[0]  = f / aspect;
        out[5]  = f;
        out[10] = (far + near) * nf;
        out[11] = -1;
        out[14] = 2 * far * near * nf;
        return out;
    },

    ortho(out, left, right, bottom, top, near, far) {
        const lr = 1.0 / (left - right);
        const bt = 1.0 / (bottom - top);
        const nf = 1.0 / (near - far);
        out.fill(0);
        out[0]  = -2 * lr;
        out[5]  = -2 * bt;
        out[10] = 2 * nf;
        out[12] = (left + right) * lr;
        out[13] = (top + bottom) * bt;
        out[14] = (far + near) * nf;
        out[15] = 1;
        return out;
    },

    multiply(out, a, b) {
        for (let i = 0; i < 4; i++) {
            const ai0 = a[i], ai1 = a[i + 4], ai2 = a[i + 8], ai3 = a[i + 12];
            out[i]      = ai0 * b[0]  + ai1 * b[1]  + ai2 * b[2]  + ai3 * b[3];
            out[i + 4]  = ai0 * b[4]  + ai1 * b[5]  + ai2 * b[6]  + ai3 * b[7];
            out[i + 8]  = ai0 * b[8]  + ai1 * b[9]  + ai2 * b[10] + ai3 * b[11];
            out[i + 12] = ai0 * b[12] + ai1 * b[13] + ai2 * b[14] + ai3 * b[15];
        }
        return out;
    },

    /** Extract the upper-left 3×3 as a flat 9-element array (column-major). */
    normalMatrix(out9, m) {
        // For a pure rotation + uniform scale model matrix, the normal matrix
        // is just the upper-left 3×3.  For non-uniform scale we'd need the
        // inverse-transpose, but all our models use uniform scale.
        out9[0] = m[0]; out9[1] = m[1]; out9[2] = m[2];
        out9[3] = m[4]; out9[4] = m[5]; out9[5] = m[6];
        out9[6] = m[8]; out9[7] = m[9]; out9[8] = m[10];
        return out9;
    },

    /** Translation matrix. */
    fromTranslation(out, x, y, z) {
        mat4.identity(out);
        out[12] = x;
        out[13] = y;
        out[14] = z;
        return out;
    },
};
