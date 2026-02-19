#!/usr/bin/env python3
"""
ASCII 3D Spinning Models
Renders rotating 3D models with ASCII shading in the terminal.
"""

import sys
import time
import math
import argparse
import os
import signal


class Vec3:
    """3D Vector class for math operations"""
    __slots__ = ['x', 'y', 'z']

    def __init__(self, x: float, y: float, z: float):
        self.x = x
        self.y = y
        self.z = z

    def dot(self, other: 'Vec3') -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def normalize(self) -> 'Vec3':
        l = math.sqrt(self.x**2 + self.y**2 + self.z**2)
        return Vec3(self.x / l, self.y / l, self.z / l) if l > 0 else Vec3(0, 0, 0)


class Quaternion:
    """Unit quaternion for rotation representation — avoids gimbal lock and drift"""
    __slots__ = ['w', 'x', 'y', 'z']

    def __init__(self, w: float, x: float, y: float, z: float):
        self.w = w
        self.x = x
        self.y = y
        self.z = z

    @staticmethod
    def from_axis_angle(axis: Vec3, angle: float) -> 'Quaternion':
        """Create a quaternion from an axis-angle rotation"""
        half = angle * 0.5
        s = math.sin(half)
        return Quaternion(math.cos(half), axis.x * s, axis.y * s, axis.z * s)

    @staticmethod
    def identity() -> 'Quaternion':
        return Quaternion(1.0, 0.0, 0.0, 0.0)

    def multiply(self, other: 'Quaternion') -> 'Quaternion':
        """Hamilton product: self * other (applies other first, then self)"""
        return Quaternion(
            self.w * other.w - self.x * other.x - self.y * other.y - self.z * other.z,
            self.w * other.x + self.x * other.w + self.y * other.z - self.z * other.y,
            self.w * other.y - self.x * other.z + self.y * other.w + self.z * other.x,
            self.w * other.z + self.x * other.y - self.y * other.x + self.z * other.w,
        )

    def normalize(self) -> 'Quaternion':
        """Re-normalize to unit quaternion (counteracts floating-point drift)"""
        n = math.sqrt(self.w**2 + self.x**2 + self.y**2 + self.z**2)
        if n > 0:
            inv = 1.0 / n
            self.w *= inv
            self.x *= inv
            self.y *= inv
            self.z *= inv
        return self

    def rotate_vector(self, v: Vec3) -> tuple:
        """Rotate a Vec3 by this quaternion: q * v * q⁻¹ (optimized, no temp Quaternion)"""
        qw, qx, qy, qz = self.w, self.x, self.y, self.z
        tx = 2.0 * (qy * v.z - qz * v.y)
        ty = 2.0 * (qz * v.x - qx * v.z)
        tz = 2.0 * (qx * v.y - qy * v.x)
        return (
            v.x + qw * tx + (qy * tz - qz * ty),
            v.y + qw * ty + (qz * tx - qx * tz),
            v.z + qw * tz + (qx * ty - qy * tx),
        )


# ---------------------------------------------------------------------------
# Model base class — any mesh defined by vertices + face index tuples
# ---------------------------------------------------------------------------

class Model:
    """Base class for 3D models defined by vertices and polygon faces.

    Subclasses provide vertex positions and face index tuples (3 or 4 indices
    per face).  Rotation, vertex rebuild, normal computation, and bounding
    radius are handled generically here.
    """

    def __init__(self, vertices: list, faces: list):
        """
        vertices : list[Vec3] — vertex positions (copied internally)
        faces    : list[tuple[int,...]] — per-face vertex index tuples (len 3 or 4)
        """
        self._original_vertices = [Vec3(v.x, v.y, v.z) for v in vertices]
        self.FACES = faces
        self.vertices = [Vec3(v.x, v.y, v.z) for v in vertices]
        self._orientation = Quaternion.identity()
        self._frame_count = 0

    # -- rotation (same for every model) ------------------------------------

    def rotate(self, angle_x: float = 0, angle_y: float = 0,
               angle_z: float = 0) -> None:
        """Quaternion-composed rotation — drift-free and gimbal-lock-free."""
        if angle_y:
            qy = Quaternion.from_axis_angle(Vec3(0, 1, 0), angle_y)
            self._orientation = qy.multiply(self._orientation)
        if angle_x:
            qx = Quaternion.from_axis_angle(Vec3(1, 0, 0), angle_x)
            self._orientation = qx.multiply(self._orientation)
        if angle_z:
            qz = Quaternion.from_axis_angle(Vec3(0, 0, 1), angle_z)
            self._orientation = qz.multiply(self._orientation)

        self._frame_count += 1
        if self._frame_count % 60 == 0:
            self._orientation.normalize()

        for orig, v in zip(self._original_vertices, self.vertices):
            v.x, v.y, v.z = self._orientation.rotate_vector(orig)

    # -- face data for the renderer -----------------------------------------

    def get_face_data(self) -> list:
        """Return [(verts, center, normal), …] for every face.

        *verts*  is a list of 3 or 4 Vec3 (transformed).
        *center* is the centroid Vec3.
        *normal* is the unit outward-normal Vec3.
        """
        result = []
        for face in self.FACES:
            vs = [self.vertices[i] for i in face]
            n = len(vs)
            center = Vec3(
                sum(v.x for v in vs) / n,
                sum(v.y for v in vs) / n,
                sum(v.z for v in vs) / n,
            )
            # Outward normal: e2 × e1  (last-edge × first-edge from v0)
            e1 = Vec3(vs[1].x - vs[0].x, vs[1].y - vs[0].y, vs[1].z - vs[0].z)
            e2 = Vec3(vs[-1].x - vs[0].x, vs[-1].y - vs[0].y, vs[-1].z - vs[0].z)
            normal = Vec3(
                e2.y * e1.z - e2.z * e1.y,
                e2.z * e1.x - e2.x * e1.z,
                e2.x * e1.y - e2.y * e1.x,
            ).normalize()
            result.append((vs, center, normal))
        return result

    # -- bounding radius for auto-fit scaling --------------------------------

    def bounding_radius(self) -> float:
        """Maximum distance from origin across all original vertices."""
        return max(
            math.sqrt(v.x ** 2 + v.y ** 2 + v.z ** 2)
            for v in self._original_vertices
        )


# ---------------------------------------------------------------------------
# Concrete models
# ---------------------------------------------------------------------------

class Cube(Model):
    """Unit cube centred at the origin, scaled by *size*."""

    def __init__(self, size: float = 1.5):
        s = size
        vertices = [
            Vec3(-s, -s, -s), Vec3(s, -s, -s), Vec3(s, s, -s), Vec3(-s, s, -s),
            Vec3(-s, -s,  s), Vec3(s, -s,  s), Vec3(s, s,  s), Vec3(-s, s,  s),
        ]
        faces = [
            (0, 1, 2, 3),   # back   (−z)
            (5, 4, 7, 6),   # front  (+z)
            (4, 0, 3, 7),   # left   (−x)
            (1, 5, 6, 2),   # right  (+x)
            (3, 2, 6, 7),   # top    (+y)
            (4, 5, 1, 0),   # bottom (−y)
        ]
        super().__init__(vertices, faces)


class Car(Model):
    """Low-poly sedan — 16 vertices, 12 quad faces.

    The car is oriented with length along Z (front = +z, rear = −z),
    width along X, and height along Y.  All coordinates are multiplied
    by *size* so the model scales uniformly.
    """

    def __init__(self, size: float = 1.0):
        s = size
        vertices = [
            # Body bottom (y = −0.5)
            Vec3(-0.80 * s, -0.50 * s,  2.00 * s),   #  0  front-left-bottom
            Vec3( 0.80 * s, -0.50 * s,  2.00 * s),   #  1  front-right-bottom
            Vec3( 0.80 * s, -0.50 * s, -2.00 * s),   #  2  rear-right-bottom
            Vec3(-0.80 * s, -0.50 * s, -2.00 * s),   #  3  rear-left-bottom

            # Belt line / body top (y = 0.0)
            Vec3(-0.80 * s,  0.00 * s,  2.00 * s),   #  4  front-left-belt
            Vec3( 0.80 * s,  0.00 * s,  2.00 * s),   #  5  front-right-belt
            Vec3( 0.80 * s,  0.00 * s, -2.00 * s),   #  6  rear-right-belt
            Vec3(-0.80 * s,  0.00 * s, -2.00 * s),   #  7  rear-left-belt

            # Windshield base (y = 0.0, z = 0.7)
            Vec3(-0.80 * s,  0.00 * s,  0.70 * s),   #  8  windshield-base-left
            Vec3( 0.80 * s,  0.00 * s,  0.70 * s),   #  9  windshield-base-right

            # Rear-window base (y = 0.0, z = −1.0)
            Vec3( 0.80 * s,  0.00 * s, -1.00 * s),   # 10  rear-window-base-right
            Vec3(-0.80 * s,  0.00 * s, -1.00 * s),   # 11  rear-window-base-left

            # Roof (y = 0.65, slightly narrower for visual interest)
            Vec3(-0.72 * s,  0.65 * s,  0.35 * s),   # 12  roof-front-left
            Vec3( 0.72 * s,  0.65 * s,  0.35 * s),   # 13  roof-front-right
            Vec3( 0.72 * s,  0.65 * s, -0.65 * s),   # 14  roof-rear-right
            Vec3(-0.72 * s,  0.65 * s, -0.65 * s),   # 15  roof-rear-left
        ]

        # All faces use CCW winding viewed from outside → e2×e1 = outward normal
        faces = [
            # --- body ---
            (0, 1, 2, 3),       # bottom         (normal −y)
            (0, 4, 5, 1),       # front bumper    (normal +z)
            (2, 6, 7, 3),       # rear bumper     (normal −z)
            (1, 5, 6, 2),       # right body side (normal +x)
            (3, 7, 4, 0),       # left body side  (normal −x)

            # --- top panels at belt line ---
            (8, 9, 5, 4),       # hood            (normal +y)
            (10, 11, 7, 6),     # trunk           (normal +y)

            # --- cabin ---
            (8, 12, 13, 9),     # windshield      (normal forward-up)
            (10, 14, 15, 11),   # rear window     (normal backward-up)
            (13, 12, 15, 14),   # roof            (normal +y)
            (9, 13, 14, 10),    # right cabin     (normal ~+x)
            (11, 15, 12, 8),    # left cabin      (normal ~−x)
        ]
        super().__init__(vertices, faces)


class HouseScene(Model):
    """A house with pitched roof, garden ground, and two trees.

    28 vertices, 19 faces (quads + triangles).  The house sits on a garden
    ground plane with a tree on each side.

    Coordinate system: X = left/right, Y = up, Z = front/back.
    """

    def __init__(self, size: float = 1.0):
        s = size
        vertices = [
            # ── Ground (indices 0–3) ──────────────────────────────────────
            Vec3(-2.30 * s, -0.02 * s, -1.80 * s),  #  0 FL
            Vec3( 2.30 * s, -0.02 * s, -1.80 * s),  #  1 FR
            Vec3( 2.30 * s, -0.02 * s,  1.80 * s),  #  2 RR
            Vec3(-2.30 * s, -0.02 * s,  1.80 * s),  #  3 RL

            # ── House body (indices 4–11) ─────────────────────────────────
            Vec3(-1.00 * s,  0.00 * s, -0.75 * s),  #  4 front-L-bottom
            Vec3( 1.00 * s,  0.00 * s, -0.75 * s),  #  5 front-R-bottom
            Vec3( 1.00 * s,  0.00 * s,  0.75 * s),  #  6 rear-R-bottom
            Vec3(-1.00 * s,  0.00 * s,  0.75 * s),  #  7 rear-L-bottom
            Vec3(-1.00 * s,  1.50 * s, -0.75 * s),  #  8 front-L-top
            Vec3( 1.00 * s,  1.50 * s, -0.75 * s),  #  9 front-R-top
            Vec3( 1.00 * s,  1.50 * s,  0.75 * s),  # 10 rear-R-top
            Vec3(-1.00 * s,  1.50 * s,  0.75 * s),  # 11 rear-L-top

            # ── Roof eaves + ridge (indices 12–17) ────────────────────────
            Vec3(-1.15 * s,  1.50 * s, -0.85 * s),  # 12 eave-front-L
            Vec3( 1.15 * s,  1.50 * s, -0.85 * s),  # 13 eave-front-R
            Vec3( 1.15 * s,  1.50 * s,  0.85 * s),  # 14 eave-rear-R
            Vec3(-1.15 * s,  1.50 * s,  0.85 * s),  # 15 eave-rear-L
            Vec3( 0.00 * s,  2.30 * s, -0.85 * s),  # 16 ridge-front
            Vec3( 0.00 * s,  2.30 * s,  0.85 * s),  # 17 ridge-rear

            # ── Tree 1 — left side (indices 18–22) ────────────────────────
            Vec3(-1.95 * s,  0.00 * s, -1.15 * s),  # 18 base FL
            Vec3(-1.25 * s,  0.00 * s, -1.15 * s),  # 19 base FR
            Vec3(-1.25 * s,  0.00 * s, -0.45 * s),  # 20 base RR
            Vec3(-1.95 * s,  0.00 * s, -0.45 * s),  # 21 base RL
            Vec3(-1.60 * s,  1.80 * s, -0.80 * s),  # 22 apex

            # ── Tree 2 — right side (indices 23–27) ───────────────────────
            Vec3( 1.35 * s,  0.00 * s,  0.35 * s),  # 23 base FL
            Vec3( 1.85 * s,  0.00 * s,  0.35 * s),  # 24 base FR
            Vec3( 1.85 * s,  0.00 * s,  0.85 * s),  # 25 base RR
            Vec3( 1.35 * s,  0.00 * s,  0.85 * s),  # 26 base RL
            Vec3( 1.60 * s,  1.20 * s,  0.60 * s),  # 27 apex
        ]

        # All faces: CCW winding from outside → e2×e1 = outward normal
        faces = [
            # Ground (double-sided so it's visible from below too)
            (0, 1, 2, 3),            # top    (normal +y)
            (3, 2, 1, 0),            # bottom (normal −y)

            # House walls (no top — roof covers it)
            (4, 5, 9, 8),            # front wall   (normal −z)
            (6, 7, 11, 10),          # back wall    (normal +z)
            (5, 6, 10, 9),           # right wall   (normal +x)
            (7, 4, 8, 11),           # left wall    (normal −x)

            # Roof
            (12, 16, 17, 15),        # left slope   (normal ←↑)
            (13, 14, 17, 16),        # right slope  (normal →↑)
            (12, 13, 16),            # front gable  (triangle, normal −z)
            (14, 15, 17),            # rear gable   (triangle, normal +z)

            # Tree 1 (pyramid)
            (18, 19, 22),            # front
            (19, 20, 22),            # right
            (20, 21, 22),            # back
            (21, 18, 22),            # left
            (18, 21, 20, 19),        # bottom (normal −y)

            # Tree 2 (pyramid)
            (23, 24, 27),            # front
            (24, 25, 27),            # right
            (25, 26, 27),            # back
            (26, 23, 27),            # left
            (23, 26, 25, 24),        # bottom (normal −y)
        ]
        super().__init__(vertices, faces)


# ---------------------------------------------------------------------------
# Renderer — supports any Model with 3- or 4-vertex faces
# ---------------------------------------------------------------------------

class Renderer:
    """ASCII renderer for any 3D Model with per-pixel point-light shading."""

    SHADING = '.:-=+*%@'
    CHAR_ASPECT = 2.0
    EDGE_STR = '\033[38;2;159;239;0m#\033[0m'

    def __init__(self, width: int, height: int, model: Model):
        self.width = width
        self.height = height
        # Auto-fit: scale so the model's bounding sphere fits the viewport
        max_extent = model.bounding_radius()
        self.scale = min(
            (width // 2 - 1) / max_extent,
            (height // 2 - 1) * self.CHAR_ASPECT / max_extent,
        )
        self.light_pos = Vec3(3.0, 4.0, 3.0)
        self.ambient = 0.12

    # -- projection ---------------------------------------------------------

    def _project_vertex(self, v: Vec3) -> tuple:
        """Orthographic projection → (screen_x, screen_y) or None."""
        x = round(v.x * self.scale + self.width // 2)
        y = round(-v.y * self.scale / self.CHAR_ASPECT + self.height // 2)
        margin = max(self.width, self.height)
        if -margin <= x < self.width + margin and -margin <= y < self.height + margin:
            return (x, y)
        return None

    # -- main render entry point --------------------------------------------

    def render(self, model: Model) -> list:
        """Render a Model into a 2-D character buffer with per-pixel z-buffering."""
        visible = []
        for vs, center, normal in model.get_face_data():
            if normal.z > 0:
                visible.append((vs, center, normal))

        buffer = [[' '] * self.width for _ in range(self.height)]
        zbuffer = [[-1e30] * self.width for _ in range(self.height)]

        # Fill faces (z-buffer handles occlusion per-pixel; no sorting needed)
        for vs, center, normal in visible:
            projected = [self._project_vertex(v) for v in vs]
            if all(projected):
                self._draw_face_lit(buffer, zbuffer, projected, vs[0], normal)

        # Edges with z-buffer depth test (small bias so edges sit in front of
        # their own face plane but behind genuinely closer geometry)
        for vs, center, normal in visible:
            projected = [self._project_vertex(v) for v in vs]
            if all(projected):
                n = len(projected)
                for i in range(n):
                    j = (i + 1) % n
                    self._draw_line(buffer, zbuffer,
                                    projected[i], projected[j],
                                    vs[i].z, vs[j].z,
                                    self.EDGE_STR, z_bias=0.005)

        return buffer

    # -- line drawing (Bresenham) -------------------------------------------

    def _draw_line(self, buffer, zbuffer, p1, p2, z1, z2, char, z_bias=0.0):
        """Bresenham line with per-pixel z-buffer depth test."""
        x1, y1 = p1
        x2, y2 = p2
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        total = max(dx, dy)
        step = 0
        while True:
            if 0 <= x1 < self.width and 0 <= y1 < self.height:
                t = step / total if total > 0 else 0.0
                z = z1 + (z2 - z1) * t + z_bias
                if z >= zbuffer[y1][x1]:
                    zbuffer[y1][x1] = z
                    buffer[y1][x1] = char
            if x1 == x2 and y1 == y2:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x1 += sx
            if e2 < dx:
                err += dx
                y1 += sy
            step += 1

    # -- per-pixel lit face fill --------------------------------------------

    def _draw_face_lit(self, buffer, zbuffer, projected, v0, normal):
        """Fill a convex polygon (3 or 4 verts) with per-pixel z-buffered point-light shading."""
        xs = [p[0] for p in projected]
        ys = [p[1] for p in projected]
        xmin = max(0, min(xs))
        xmax = min(self.width - 1, max(xs))
        ymin = max(0, min(ys))
        ymax = min(self.height - 1, max(ys))

        cx = self.width // 2
        cy = self.height // 2
        inv_scale = 1.0 / self.scale

        nx, ny, nz = normal.x, normal.y, normal.z
        nz_inv = 1.0 / nz if abs(nz) > 1e-10 else 0.0
        v0x, v0y, v0z = v0.x, v0.y, v0.z

        lx, ly, lz = self.light_pos.x, self.light_pos.y, self.light_pos.z
        shading = self.SHADING
        num_shades = len(shading) - 1
        ambient = self.ambient
        _sqrt = math.sqrt
        n_verts = len(projected)

        for y in range(ymin, ymax + 1):
            wy = -(y - cy) * self.CHAR_ASPECT * inv_scale
            for x in range(xmin, xmax + 1):
                if self._point_in_polygon(x, y, projected, n_verts):
                    wx = (x - cx) * inv_scale
                    wz = v0z - (nx * (wx - v0x) + ny * (wy - v0y)) * nz_inv

                    # Z-buffer depth test — only draw if this pixel is
                    # closer to the camera (higher z) than what's there
                    if wz < zbuffer[y][x]:
                        continue
                    zbuffer[y][x] = wz

                    dx = lx - wx
                    dy = ly - wy
                    dz = lz - wz
                    dist = _sqrt(dx * dx + dy * dy + dz * dz)
                    if dist > 0:
                        inv_d = 1.0 / dist
                        diffuse = max(0.0, nx * dx * inv_d
                                       + ny * dy * inv_d
                                       + nz * dz * inv_d)
                        atten = 1.0 / (1.0 + 0.02 * dist * dist)
                        brightness = ambient + (1.0 - ambient) * diffuse * atten
                    else:
                        brightness = 1.0

                    idx = int(brightness * num_shades)
                    buffer[y][x] = shading[max(0, min(num_shades, idx))]

    # -- convex polygon containment test ------------------------------------

    @staticmethod
    def _point_in_polygon(px, py, projected, n):
        """Cross-product sign test for a convex polygon (3 or 4 verts)."""
        pos = neg = False
        for i in range(n):
            ax, ay = projected[i]
            bx, by = projected[(i + 1) % n]
            d = (px - bx) * (ay - by) - (ax - bx) * (py - by)
            if d > 0:
                pos = True
            elif d < 0:
                neg = True
            if pos and neg:
                return False
        return True

    # -- buffer → string ----------------------------------------------------

    def buffer_to_string(self, buffer):
        return '\n'.join(''.join(row) for row in buffer)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

MODELS = {
    'cube':  Cube,
    'car':   Car,
    'house': HouseScene,
}


class SpinningModel:
    """Main application class — works with any Model."""

    def __init__(self, args):
        self.args = args
        model_cls = MODELS[args.model]
        self.model = model_cls(args.size)
        self.renderer = Renderer(args.width, args.height, self.model)
        self.running = True
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        self.running = False
        print()

    def update(self):
        self.model.rotate(
            self.args.speed_x,
            self.args.speed_y,
            self.args.speed_z if self.args.rotate_z else 0,
        )

    def render(self):
        buffer = self.renderer.render(self.model)
        sys.stdout.write('\033[2J\033[H' if os.name != 'nt' else '\x1b[2J\x1b[H')
        sys.stdout.write(self.renderer.buffer_to_string(buffer))
        sys.stdout.flush()

    def run(self):
        frame_time = 1.0 / self.args.fps
        while self.running:
            start = time.time()
            self.update()
            self.render()
            time.sleep(max(0, frame_time - (time.time() - start)))


def get_terminal_size():
    try:
        s = os.get_terminal_size()
        return s.columns, s.lines
    except OSError:
        return 80, 24


def main():
    parser = argparse.ArgumentParser(
        description='Render a spinning 3D model in ASCII art',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    w, h = get_terminal_size()
    parser.add_argument('--model', '-m', choices=sorted(MODELS),
                        default='cube', help='Model to render (default: cube)')
    parser.add_argument('--width', '-w', type=int, default=w,
                        help=f'Console width (default: {w})')
    parser.add_argument('--height', '-H', type=int, default=h - 1,
                        help=f'Console height (default: {h - 1})')
    parser.add_argument('--size', '-s', type=float, default=1.5,
                        help='Model size multiplier (default: 1.5)')
    parser.add_argument('--fps', '-f', type=int, default=30,
                        help='Frames per second (default: 30)')
    parser.add_argument('--speed-y', type=float, default=0.03,
                        help='Y rotation speed (default: 0.03)')
    parser.add_argument('--speed-x', type=float, default=0.01,
                        help='X rotation speed (default: 0.01)')
    parser.add_argument('--speed-z', type=float, default=0.02,
                        help='Z rotation speed (default: 0.02)')
    parser.add_argument('--rotate-z', action='store_true',
                        help='Enable Z-axis rotation')
    parser.add_argument('--frame', '-fr', type=int, default=None,
                        help='Render a specific frame and exit')

    args = parser.parse_args()

    if not 1 <= args.fps <= 120:
        sys.exit('Error: FPS must be between 1 and 120')
    if args.width < 20 or args.height < 10:
        sys.exit('Error: Width >= 20 and height >= 10 required')

    app = SpinningModel(args)
    if args.frame is not None:
        for _ in range(args.frame):
            app.update()
        app.render()
        print()
    else:
        app.run()


if __name__ == '__main__':
    main()
