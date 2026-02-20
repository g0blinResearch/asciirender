/**
 * camera.js — First-person camera with yaw/pitch orientation.
 *
 * Direct port of the Camera class from run.py.
 * Default orientation (yaw=0, pitch=0) looks toward −Z.
 *
 * Produces a 4×4 view matrix for WebGL uniform upload.
 */

import { Vec3, mat4 } from './math.js';

export class Camera {
    constructor(position = null, yaw = 0.0, pitch = 0.0) {
        this.position = position || new Vec3(0, 0, 5);
        this.yaw = yaw;       // radians around world Y; 0 = facing −Z
        this.pitch = pitch;    // radians; positive = look upward
        this.forward = new Vec3(0, 0, -1);
        this.right = new Vec3(1, 0, 0);
        this.up = new Vec3(0, 1, 0);
        this._viewMatrix = mat4.create();
        this._updateVectors();
    }

    _updateVectors() {
        const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw);
        const cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
        this.forward = new Vec3(sy * cp, sp, -cy * cp);
        this.right = new Vec3(cy, 0, sy);
        this.up = new Vec3(-sy * sp, cp, cy * sp);
    }

    moveForward(dist) {
        const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw);
        this.position.x += sy * dist;
        this.position.z -= cy * dist;
    }

    moveRight(dist) {
        this.position.x += this.right.x * dist;
        this.position.z += this.right.z * dist;
    }

    moveUp(dist) {
        this.position.y += dist;
    }

    turn(dyaw, dpitch = 0) {
        this.yaw += dyaw;
        this.pitch = Math.max(-1.3, Math.min(1.3, this.pitch + dpitch));
        this._updateVectors();
    }

    /**
     * Build and return the 4×4 view matrix (column-major).
     * This is the lookAt matrix: rows are right, up, -forward.
     */
    getViewMatrix() {
        const m = this._viewMatrix;
        const r = this.right, u = this.up, f = this.forward;
        const p = this.position;

        // Column-major layout:
        //   col0 = right.x, up.x, -forward.x, 0
        //   col1 = right.y, up.y, -forward.y, 0
        //   col2 = right.z, up.z, -forward.z, 0
        //   col3 = -dot(right,pos), -dot(up,pos), dot(forward,pos), 1

        m[0]  = r.x;     m[1]  = u.x;     m[2]  = -f.x;    m[3]  = 0;
        m[4]  = r.y;     m[5]  = u.y;     m[6]  = -f.y;    m[7]  = 0;
        m[8]  = r.z;     m[9]  = u.z;     m[10] = -f.z;    m[11] = 0;
        m[12] = -(r.x * p.x + r.y * p.y + r.z * p.z);
        m[13] = -(u.x * p.x + u.y * p.y + u.z * p.z);
        m[14] = (f.x * p.x + f.y * p.y + f.z * p.z);
        m[15] = 1;

        return m;
    }
}
