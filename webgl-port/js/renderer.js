/**
 * renderer.js — WebGL renderer with fill and wireframe shaders.
 *
 * Handles shader compilation, buffer management, and draw calls.
 * Supports orthographic (spin mode) and perspective (move mode) projection.
 */

import { Vec3, Quaternion, mat4 } from './math.js';

// ── Shader sources ──────────────────────────────────────────────────────

const FILL_VERTEX = `
attribute vec3 aPosition;
attribute vec3 aNormal;

uniform mat4 uProjection;
uniform mat4 uView;
uniform mat4 uModel;
uniform mat3 uNormalMatrix;

varying vec3 vWorldPos;
varying vec3 vNormal;
varying float vCamDist;

void main() {
    vec4 worldPos = uModel * vec4(aPosition, 1.0);
    vec4 viewPos = uView * worldPos;
    gl_Position = uProjection * viewPos;
    vWorldPos = worldPos.xyz;
    vNormal = uNormalMatrix * aNormal;
    vCamDist = -viewPos.z;
}
`;

const FILL_FRAGMENT = `
precision mediump float;

uniform vec3 uLightPos;
uniform float uAmbient;
uniform float uFogDistance;
uniform vec3 uFogColor;

varying vec3 vWorldPos;
varying vec3 vNormal;
varying float vCamDist;

void main() {
    vec3 N = normalize(vNormal);
    vec3 L = uLightPos - vWorldPos;
    float dist = length(L);
    L = L / dist;
    float diff = max(dot(N, L), 0.0);
    float atten = 1.0 / (1.0 + 0.02 * dist * dist);
    float brightness = uAmbient + (1.0 - uAmbient) * diff * atten;

    // Distance fog (quadratic)
    if (uFogDistance > 0.0) {
        float fog = clamp(vCamDist / uFogDistance, 0.0, 1.0);
        brightness *= 1.0 - fog * fog;
    }

    vec3 color = vec3(brightness);

    // Blend toward fog color for distant pixels
    if (uFogDistance > 0.0) {
        float fog = clamp(vCamDist / uFogDistance, 0.0, 1.0);
        color = mix(color, uFogColor, fog * fog);
    }

    gl_FragColor = vec4(color, 1.0);
}
`;

const WIRE_VERTEX = `
attribute vec3 aPosition;

uniform mat4 uProjection;
uniform mat4 uView;
uniform mat4 uModel;

varying float vCamDist;

void main() {
    vec4 viewPos = uView * uModel * vec4(aPosition, 1.0);
    gl_Position = uProjection * viewPos;
    vCamDist = -viewPos.z;
}
`;

const WIRE_FRAGMENT = `
precision mediump float;

uniform vec3 uEdgeColor;
uniform float uFogDistance;

varying float vCamDist;

void main() {
    vec3 color = uEdgeColor;
    if (uFogDistance > 0.0) {
        float fog = clamp(vCamDist / uFogDistance, 0.0, 1.0);
        color *= 1.0 - fog * fog;
    }
    // Discard fully fogged edges
    if (color.r + color.g + color.b < 0.01) discard;
    gl_FragColor = vec4(color, 1.0);
}
`;


// ── Sky shaders ─────────────────────────────────────────────────────────

const SKY_VERTEX = `
attribute vec2 aPosition;

varying vec2 vUV;

void main() {
    vUV = aPosition * 0.5 + 0.5;
    gl_Position = vec4(aPosition, 0.9999, 1.0);
}
`;

const SKY_FRAGMENT = `
precision mediump float;

uniform float uHorizonY;
uniform vec3 uSkyColorHigh;
uniform vec3 uSkyColorLow;
uniform vec3 uGroundColor;

varying vec2 vUV;

void main() {
    // vUV.y: 0 = bottom of screen, 1 = top of screen
    float y = vUV.y;
    // Convert uHorizonY (0=top, 1=bottom) to bottom-up convention
    float horizonNorm = 1.0 - uHorizonY;

    if (y < horizonNorm - 0.004) {
        // Below horizon — ground/fog colour, fading darker further down.
        // This matches the fog colour so distant geometry blends seamlessly
        // into the background rather than floating above a dark band.
        float depth = clamp((horizonNorm - y) / max(horizonNorm, 0.001), 0.0, 1.0);
        float fade = max(0.3, 1.0 - depth * 0.7);
        gl_FragColor = vec4(uGroundColor * fade, 1.0);
    } else if (y < horizonNorm + 0.004) {
        // Horizon band — brighter
        float t = smoothstep(horizonNorm - 0.004, horizonNorm + 0.004, y);
        vec3 col = mix(uGroundColor, uSkyColorLow * 1.4, t);
        gl_FragColor = vec4(col, 1.0);
    } else {
        // Sky above horizon — gradient from horizon colour to zenith
        float t = clamp((y - horizonNorm) / max(1.0 - horizonNorm, 0.001), 0.0, 1.0);
        vec3 col = mix(uSkyColorLow, uSkyColorHigh, t);
        gl_FragColor = vec4(col, 1.0);
    }
}
`;


// ── WebGL helper functions ──────────────────────────────────────────────

function compileShader(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error('Shader compile error:', gl.getShaderInfoLog(shader));
        gl.deleteShader(shader);
        return null;
    }
    return shader;
}

function createProgram(gl, vsSource, fsSource) {
    const vs = compileShader(gl, gl.VERTEX_SHADER, vsSource);
    const fs = compileShader(gl, gl.FRAGMENT_SHADER, fsSource);
    const prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
        console.error('Program link error:', gl.getProgramInfoLog(prog));
        return null;
    }
    return prog;
}

function getUniformLocations(gl, program, names) {
    const locs = {};
    for (const name of names) {
        locs[name] = gl.getUniformLocation(program, name);
    }
    return locs;
}


// ── Renderer ────────────────────────────────────────────────────────────

export class Renderer {
    constructor(canvas) {
        this.canvas = canvas;
        const gl = canvas.getContext('webgl', { antialias: true, alpha: false });
        if (!gl) throw new Error('WebGL not supported');
        this.gl = gl;

        // Compile shader programs
        this.fillProg = createProgram(gl, FILL_VERTEX, FILL_FRAGMENT);
        this.wireProg = createProgram(gl, WIRE_VERTEX, WIRE_FRAGMENT);

        // Cache uniform locations
        this.fillUniforms = getUniformLocations(gl, this.fillProg, [
            'uProjection', 'uView', 'uModel', 'uNormalMatrix',
            'uLightPos', 'uAmbient', 'uFogDistance', 'uFogColor',
        ]);
        this.wireUniforms = getUniformLocations(gl, this.wireProg, [
            'uProjection', 'uView', 'uModel',
            'uEdgeColor', 'uFogDistance',
        ]);

        // Attribute locations
        this.fillAttribs = {
            aPosition: gl.getAttribLocation(this.fillProg, 'aPosition'),
            aNormal: gl.getAttribLocation(this.fillProg, 'aNormal'),
        };
        this.wireAttribs = {
            aPosition: gl.getAttribLocation(this.wireProg, 'aPosition'),
        };

        // Reusable matrices
        this._projMatrix = mat4.create();
        this._modelMatrix = mat4.create();
        this._normalMat3 = new Float32Array(9);

        // Settings
        this.lightPos = new Vec3(3, 4, 3);
        this.ambient = 0.12;
        this.fogDistance = 0;
        this.fogColor = [0, 0, 0];
        this.drawEdges = true;

        // Object edge color: bright green matching #9fef00
        this.objectEdgeColor = [159 / 255, 239 / 255, 0];
        // Terrain wireframe color: sage green
        this.terrainEdgeColor = [60 / 255, 90 / 255, 45 / 255];

        // GL state
        gl.enable(gl.DEPTH_TEST);
        gl.depthFunc(gl.LEQUAL);
        gl.clearColor(0, 0, 0, 1);
        gl.enable(gl.CULL_FACE);
        gl.cullFace(gl.BACK);

        // For wireframe depth bias
        gl.enable(gl.POLYGON_OFFSET_FILL);

        // ── Sky pass setup ──────────────────────────────────────────────
        this.skyProg = createProgram(gl, SKY_VERTEX, SKY_FRAGMENT);
        this.skyUniforms = getUniformLocations(gl, this.skyProg, [
            'uHorizonY', 'uSkyColorHigh', 'uSkyColorLow', 'uGroundColor',
        ]);
        this.skyAttribs = {
            aPosition: gl.getAttribLocation(this.skyProg, 'aPosition'),
        };

        // Full-screen quad (two triangles)
        this._skyQuadBuf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, this._skyQuadBuf);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
            -1, -1,  1, -1,  -1, 1,
            -1,  1,  1, -1,   1, 1,
        ]), gl.STATIC_DRAW);

        // Sky colour palette
        this.skyColorHigh = [0.04, 0.05, 0.09];  // dark blue-grey zenith
        this.skyColorLow  = [0.16, 0.18, 0.23];  // brighter at horizon
        this.groundColor  = [0.17, 0.19, 0.24];  // matches fog colour — seamless blend
    }

    resize() {
        const dpr = window.devicePixelRatio || 1;
        const w = this.canvas.clientWidth;
        const h = this.canvas.clientHeight;
        if (this.canvas.width !== w * dpr || this.canvas.height !== h * dpr) {
            this.canvas.width = w * dpr;
            this.canvas.height = h * dpr;
            this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
        }
    }

    /** Get canvas aspect ratio. */
    get aspect() {
        return this.canvas.width / this.canvas.height;
    }

    // ── Buffer management ────────────────────────────────────────────────

    /**
     * Create WebGL buffers from geometry data.
     * Returns an object with buffer handles.
     */
    createBuffers(geo) {
        const gl = this.gl;
        const buf = {};

        buf.position = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buf.position);
        gl.bufferData(gl.ARRAY_BUFFER, geo.positions, gl.STATIC_DRAW);

        buf.normal = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buf.normal);
        gl.bufferData(gl.ARRAY_BUFFER, geo.normals, gl.STATIC_DRAW);

        buf.index = gl.createBuffer();
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, buf.index);
        gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, geo.indices, gl.STATIC_DRAW);
        buf.indexCount = geo.indices.length;

        buf.edgeIndex = gl.createBuffer();
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, buf.edgeIndex);
        gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, geo.edgeIndices, gl.STATIC_DRAW);
        buf.edgeIndexCount = geo.edgeIndices.length;

        return buf;
    }

    /** Delete WebGL buffers. */
    deleteBuffers(buf) {
        if (!buf) return;
        const gl = this.gl;
        if (buf.position) gl.deleteBuffer(buf.position);
        if (buf.normal) gl.deleteBuffer(buf.normal);
        if (buf.index) gl.deleteBuffer(buf.index);
        if (buf.edgeIndex) gl.deleteBuffer(buf.edgeIndex);
    }

    // ── Projection setup ─────────────────────────────────────────────────

    setPerspective(fovDegHorizontal) {
        // Convert horizontal FOV to vertical FOV (mat4.perspective expects vertical)
        const fovRadH = fovDegHorizontal * Math.PI / 180;
        const fovRadV = 2 * Math.atan(Math.tan(fovRadH / 2) / this.aspect);
        mat4.perspective(this._projMatrix, fovRadV, this.aspect, 0.01, 500);
    }

    setOrthographic(halfExtent) {
        const a = this.aspect;
        mat4.ortho(this._projMatrix,
            -halfExtent * a, halfExtent * a,
            -halfExtent, halfExtent,
            -100, 100);
    }

    // ── Draw calls ───────────────────────────────────────────────────────

    beginFrame() {
        const gl = this.gl;
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    }

    /**
     * Draw a full-screen sky gradient behind all geometry.
     * @param {number} cameraPitch — camera pitch in radians
     */
    drawSky(cameraPitch) {
        const gl = this.gl;

        gl.useProgram(this.skyProg);
        gl.depthMask(false);
        gl.disable(gl.DEPTH_TEST);

        // Horizon Y in normalised screen space [0=top, 1=bottom]
        // pitch=0 → horizon at 0.5; pitch up → horizon moves down
        const horizonY = Math.min(1.0, Math.max(0.0,
            0.5 + Math.tan(cameraPitch) * 0.4));

        gl.uniform1f(this.skyUniforms.uHorizonY, horizonY);
        gl.uniform3fv(this.skyUniforms.uSkyColorHigh, this.skyColorHigh);
        gl.uniform3fv(this.skyUniforms.uSkyColorLow, this.skyColorLow);
        gl.uniform3fv(this.skyUniforms.uGroundColor, this.groundColor);

        gl.bindBuffer(gl.ARRAY_BUFFER, this._skyQuadBuf);
        gl.enableVertexAttribArray(this.skyAttribs.aPosition);
        gl.vertexAttribPointer(this.skyAttribs.aPosition, 2, gl.FLOAT, false, 0, 0);

        gl.drawArrays(gl.TRIANGLES, 0, 6);

        gl.enable(gl.DEPTH_TEST);
        gl.depthMask(true);
    }

    /**
     * Draw filled triangles for a set of buffers.
     * @param {Object} buf - Buffer object from createBuffers
     * @param {Float32Array} viewMatrix - 4×4 view matrix
     * @param {Float32Array} modelMatrix - 4×4 model matrix
     */
    drawFill(buf, viewMatrix, modelMatrix) {
        if (!buf || buf.indexCount === 0) return;
        const gl = this.gl;

        gl.useProgram(this.fillProg);
        gl.polygonOffset(1.0, 1.0);  // push filled faces back so edges are visible

        // Uniforms
        gl.uniformMatrix4fv(this.fillUniforms.uProjection, false, this._projMatrix);
        gl.uniformMatrix4fv(this.fillUniforms.uView, false, viewMatrix);
        gl.uniformMatrix4fv(this.fillUniforms.uModel, false, modelMatrix);

        mat4.normalMatrix(this._normalMat3, modelMatrix);
        gl.uniformMatrix3fv(this.fillUniforms.uNormalMatrix, false, this._normalMat3);

        gl.uniform3f(this.fillUniforms.uLightPos,
            this.lightPos.x, this.lightPos.y, this.lightPos.z);
        gl.uniform1f(this.fillUniforms.uAmbient, this.ambient);
        gl.uniform1f(this.fillUniforms.uFogDistance, this.fogDistance);
        gl.uniform3fv(this.fillUniforms.uFogColor, this.fogColor);

        // Attributes
        gl.bindBuffer(gl.ARRAY_BUFFER, buf.position);
        gl.enableVertexAttribArray(this.fillAttribs.aPosition);
        gl.vertexAttribPointer(this.fillAttribs.aPosition, 3, gl.FLOAT, false, 0, 0);

        gl.bindBuffer(gl.ARRAY_BUFFER, buf.normal);
        gl.enableVertexAttribArray(this.fillAttribs.aNormal);
        gl.vertexAttribPointer(this.fillAttribs.aNormal, 3, gl.FLOAT, false, 0, 0);

        // Draw
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, buf.index);
        gl.drawElements(gl.TRIANGLES, buf.indexCount, gl.UNSIGNED_SHORT, 0);
    }

    /**
     * Draw wireframe edges for a set of buffers.
     * @param {Object} buf - Buffer object from createBuffers
     * @param {Float32Array} viewMatrix - 4×4 view matrix
     * @param {Float32Array} modelMatrix - 4×4 model matrix
     * @param {number[]} edgeColor - [r, g, b] normalized color
     */
    drawWireframe(buf, viewMatrix, modelMatrix, edgeColor = null) {
        if (!buf || buf.edgeIndexCount === 0) return;
        const gl = this.gl;

        gl.useProgram(this.wireProg);
        gl.polygonOffset(0, 0);

        // Uniforms
        gl.uniformMatrix4fv(this.wireUniforms.uProjection, false, this._projMatrix);
        gl.uniformMatrix4fv(this.wireUniforms.uView, false, viewMatrix);
        gl.uniformMatrix4fv(this.wireUniforms.uModel, false, modelMatrix);

        const color = edgeColor || this.objectEdgeColor;
        gl.uniform3f(this.wireUniforms.uEdgeColor, color[0], color[1], color[2]);
        gl.uniform1f(this.wireUniforms.uFogDistance, this.fogDistance);

        // Attributes
        gl.bindBuffer(gl.ARRAY_BUFFER, buf.position);
        gl.enableVertexAttribArray(this.wireAttribs.aPosition);
        gl.vertexAttribPointer(this.wireAttribs.aPosition, 3, gl.FLOAT, false, 0, 0);

        // Draw
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, buf.edgeIndex);
        gl.drawElements(gl.LINES, buf.edgeIndexCount, gl.UNSIGNED_SHORT, 0);
    }

    /**
     * Convenience: draw fill + wireframe for a model.
     */
    drawModel(buf, viewMatrix, modelMatrix, edgeColor = null) {
        // Disable face culling for models so both sides are visible
        // (matching Python's perspective renderer which disables back-face culling)
        const gl = this.gl;
        gl.disable(gl.CULL_FACE);
        this.drawFill(buf, viewMatrix, modelMatrix);
        if (this.drawEdges) {
            this.drawWireframe(buf, viewMatrix, modelMatrix, edgeColor);
        }
        gl.enable(gl.CULL_FACE);
    }

    /**
     * Draw terrain wireframe only (no fill) — for terrain grid.
     */
    drawTerrainWireframe(buf, viewMatrix, modelMatrix) {
        if (!buf || buf.edgeIndexCount === 0) return;
        const gl = this.gl;

        // Draw terrain fill first (dark, subtle)
        gl.disable(gl.CULL_FACE);
        this.drawFill(buf, viewMatrix, modelMatrix);
        gl.enable(gl.CULL_FACE);

        // Then wireframe edges in sage green
        this.drawWireframe(buf, viewMatrix, modelMatrix, this.terrainEdgeColor);
    }
    
    /**
     * Draw yellow path markers from spawn to special tree.
     * Uses golden/yellow color for the path.
     */
    drawPath(buf, viewMatrix, modelMatrix) {
        if (!buf || buf.edgeIndexCount === 0) return;
        
        // Yellow/golden path color
        const pathColor = [1.0, 0.85, 0.2];
        
        // Draw path fill and wireframe
        const gl = this.gl;
        gl.disable(gl.CULL_FACE);
        this.drawFill(buf, viewMatrix, modelMatrix);
        this.drawWireframe(buf, viewMatrix, modelMatrix, pathColor);
        gl.enable(gl.CULL_FACE);
    }
}
