#!/usr/bin/env python3
"""
ASCII 3D Spinning Models
Renders rotating 3D models with ASCII shading in the terminal.

Supports two modes toggled at runtime with Tab:
  SPIN  — model auto-rotates (orthographic projection)
  MOVE  — free camera navigation with perspective projection

Movement-mode controls:
  W / Up-arrow    Move forward        S / Down-arrow  Move backward
  A               Strafe left         D               Strafe right
  Left-arrow      Turn left           Right-arrow     Turn right
  R / Space       Move up             F               Move down
  E               Pitch up            C               Pitch down
  Tab             Switch to SPIN      Q / Ctrl-C      Quit

Forest mode (--forest):
  Procedurally generated infinite forest with trees, rocks, and bushes.
  Uses chunk-based streaming — new terrain loads as you walk.
  Navigate with WASD + arrow keys.  Seed controls the world layout.
"""

import sys
import time
import math
import argparse
import os
import signal
import random

# Non-blocking keyboard input (Unix only)
try:
    import termios
    import select
    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False


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
# Camera — first-person with yaw/pitch orientation
# ---------------------------------------------------------------------------

class Camera:
    """First-person camera with position and yaw/pitch orientation.

    Default orientation (yaw=0, pitch=0) looks toward −Z.

    Camera space axes:
      +X = right,  +Y = up,  cam_z = depth along the forward direction
      (cam_z > 0 ⟹ in front of the camera)
    """

    def __init__(self, position: Vec3 = None, yaw: float = 0.0,
                 pitch: float = 0.0):
        self.position = position or Vec3(0.0, 0.0, 5.0)
        self.yaw = yaw        # radians around world Y; 0 = facing −Z
        self.pitch = pitch    # radians; positive = look upward
        self._update_vectors()

    # -- orientation vectors -------------------------------------------------

    def _update_vectors(self):
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        self.forward = Vec3(sy * cp, sp, -cy * cp)
        self.right   = Vec3(cy, 0.0, sy)
        self.up      = Vec3(-sy * sp, cp, cy * sp)

    # -- movement ------------------------------------------------------------

    def move_forward(self, dist: float):
        """Move along the *horizontal* forward direction (pitch ignored)."""
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        self.position.x += sy * dist
        self.position.z -= cy * dist

    def move_right(self, dist: float):
        self.position.x += self.right.x * dist
        self.position.z += self.right.z * dist

    def move_up(self, dist: float):
        self.position.y += dist

    def turn(self, dyaw: float, dpitch: float = 0.0):
        self.yaw += dyaw
        self.pitch = max(-1.3, min(1.3, self.pitch + dpitch))
        self._update_vectors()

    # -- transforms ----------------------------------------------------------

    def view_transform(self, vx: float, vy: float, vz: float) -> tuple:
        """World → camera space.  Returns (cam_x, cam_y, cam_z)."""
        dx = vx - self.position.x
        dy = vy - self.position.y
        dz = vz - self.position.z
        return (
            self.right.x * dx + self.right.y * dy + self.right.z * dz,
            self.up.x * dx    + self.up.y * dy    + self.up.z * dz,
            self.forward.x * dx + self.forward.y * dy + self.forward.z * dz,
        )

    def transform_direction(self, nx: float, ny: float,
                            nz: float) -> tuple:
        """Rotate a direction from world space to camera space."""
        return (
            self.right.x * nx + self.right.y * ny + self.right.z * nz,
            self.up.x * nx    + self.up.y * ny    + self.up.z * nz,
            self.forward.x * nx + self.forward.y * ny + self.forward.z * nz,
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
# Forest model primitives — factory functions returning pre-computed face data
# ---------------------------------------------------------------------------

def _make_face(verts, reverse=False):
    """Build a (verts, center, normal) tuple from a list of Vec3 vertices.

    Uses e2×e1 (last_edge × first_edge from v0) for outward normal,
    matching Model.get_face_data() convention.
    """
    vs = list(reversed(verts)) if reverse else list(verts)
    n = len(vs)
    center = Vec3(
        sum(v.x for v in vs) / n,
        sum(v.y for v in vs) / n,
        sum(v.z for v in vs) / n,
    )
    e1 = Vec3(vs[1].x - vs[0].x, vs[1].y - vs[0].y, vs[1].z - vs[0].z)
    e2 = Vec3(vs[-1].x - vs[0].x, vs[-1].y - vs[0].y, vs[-1].z - vs[0].z)
    normal = Vec3(
        e2.y * e1.z - e2.z * e1.y,
        e2.z * e1.x - e2.x * e1.z,
        e2.x * e1.y - e2.y * e1.x,
    ).normalize()
    return (vs, center, normal)


def _rotate_y(lx, lz, cos_a, sin_a):
    """Rotate a point around the Y axis by a pre-computed cos/sin pair."""
    return lx * cos_a + lz * sin_a, -lx * sin_a + lz * cos_a


def make_pine_tree(wx, wz, height, angle, rng, base_y=0.0):
    """Generate face data for a multi-tier pine tree at world position (wx, base_y, wz).

    Returns a list of (verts, center, normal) tuples.

    Geometry: 4-quad trunk + 3 stacked pyramid tiers (4 tri faces each) = 16 faces.
    The layered canopy creates a recognisable spruce/pine silhouette.

    ::

             /\\
            /  \\          ← Tier 3 (smallest)
           /----\\
          /      \\        ← Tier 2 (medium)
         /--------\\
        /          \\      ← Tier 1 (largest)
       /------------\\
            ||             ← Trunk
            ||
    """
    faces = []
    ca, sa = math.cos(angle), math.sin(angle)

    # Trunk dimensions
    tw = 0.10                   # trunk half-width
    th = height * 0.40          # trunk height (shorter to leave room for 3 tiers)

    # Trunk: 4 vertical side quads
    trunk_verts = []
    for lx, lz in [(-tw, -tw), (tw, -tw), (tw, tw), (-tw, tw)]:
        rx, rz = _rotate_y(lx, lz, ca, sa)
        trunk_verts.append((
            Vec3(wx + rx, base_y, wz + rz),
            Vec3(wx + rx, base_y + th, wz + rz),
        ))

    for i in range(4):
        j = (i + 1) % 4
        b0, t0 = trunk_verts[i]
        b1, t1 = trunk_verts[j]
        faces.append(_make_face([b0, b1, t1, t0]))

    # 3 stacked canopy tiers — each is a pyramid, progressively smaller
    canopy_start = th * 0.70     # canopy begins below trunk top (overlap)
    canopy_height = height - canopy_start
    tier_count = 3
    tier_h = canopy_height / tier_count

    for t in range(tier_count):
        # Each tier: base at tier_base_y, apex at tier_apex_y
        tier_base_y = canopy_start + t * tier_h * 0.65  # overlap successive tiers
        tier_apex_y = canopy_start + (t + 1) * tier_h + t * tier_h * 0.05

        # Tier radius shrinks with height (wider at bottom, narrower at top)
        progress = t / tier_count   # 0 = bottom tier, 1 = top
        tier_radius = height * (0.38 - 0.10 * progress)

        apex = Vec3(wx, base_y + tier_apex_y, wz)
        tier_base = []
        for lx, lz in [(-tier_radius, -tier_radius),
                        (tier_radius, -tier_radius),
                        (tier_radius, tier_radius),
                        (-tier_radius, tier_radius)]:
            rx, rz = _rotate_y(lx, lz, ca, sa)
            tier_base.append(Vec3(wx + rx, base_y + tier_base_y, wz + rz))

        for i in range(4):
            j = (i + 1) % 4
            faces.append(_make_face([tier_base[i], tier_base[j], apex]))

    return faces


def make_rock(wx, wz, scale, angle, rng, base_y=0.0):
    """Generate face data for an irregular rock at world position (wx, base_y, wz).

    Geometry: irregular tetrahedron = 4 triangular faces.
    """
    faces = []
    ca, sa = math.cos(angle), math.sin(angle)

    rh = scale * (0.3 + rng.random() * 0.3)
    rw = scale * 0.5

    # Irregular tetrahedron with slightly off-centre apex
    offx = scale * (rng.random() - 0.5) * 0.3
    offz = scale * (rng.random() - 0.5) * 0.3

    pts_local = [
        (-rw, base_y, -rw * 0.7),
        (rw, base_y, -rw * 0.5),
        (rw * 0.3, base_y, rw),
        (offx, base_y + rh, offz),
    ]

    pts = []
    for lx, ly, lz in pts_local:
        rx, rz = _rotate_y(lx, lz, ca, sa)
        pts.append(Vec3(wx + rx, ly, wz + rz))

    faces.append(_make_face([pts[0], pts[1], pts[3]]))
    faces.append(_make_face([pts[1], pts[2], pts[3]]))
    faces.append(_make_face([pts[2], pts[0], pts[3]]))
    faces.append(_make_face([pts[0], pts[2], pts[1]]))   # bottom
    return faces


def make_bush(wx, wz, scale, angle, rng, base_y=0.0):
    """Generate face data for a bush at world position (wx, base_y, wz).

    Geometry: low pyramid = 4 triangular faces.
    """
    faces = []
    ca, sa = math.cos(angle), math.sin(angle)

    bw = scale * 0.4           # base half-width
    bh = scale * 0.35          # height
    apex = Vec3(wx, base_y + bh, wz)

    base = []
    for lx, lz in [(-bw, -bw), (bw, -bw), (bw, bw), (-bw, bw)]:
        rx, rz = _rotate_y(lx, lz, ca, sa)
        base.append(Vec3(wx + rx, base_y, wz + rz))

    for i in range(4):
        j = (i + 1) % 4
        faces.append(_make_face([base[i], base[j], apex]))

    return faces


def make_oak_tree(wx, wz, height, angle, rng, base_y=0.0):
    r"""Generate face data for a broadleaf oak tree at world position (wx, base_y, wz).

    Returns a list of (verts, center, normal) tuples.

    Geometry: 4-quad trunk + single large rounded canopy (sphere-like, 8 triangular faces).
    This creates a distinctive golden oak silhouette quite different from pine trees.

    ::

              _______
             /       \        ← Canopy (sphere approximation)
            /_________\
               ||||           ← Trunk
               ||
    """
    faces = []
    ca, sa = math.cos(angle), math.sin(angle)

    # Trunk dimensions — thicker than pine
    tw = 0.15                   # trunk half-width (0.15 vs 0.10 for pine)
    th = height * 0.45          # trunk height (45% of total)

    # Trunk: 4 vertical side quads
    trunk_verts = []
    for lx, lz in [(-tw, -tw), (tw, -tw), (tw, tw), (-tw, tw)]:
        rx, rz = _rotate_y(lx, lz, ca, sa)
        trunk_verts.append((
            Vec3(wx + rx, base_y, wz + rz),
            Vec3(wx + rx, base_y + th, wz + rz),
        ))

    for i in range(4):
        j = (i + 1) % 4
        b0, t0 = trunk_verts[i]
        b1, t1 = trunk_verts[j]
        faces.append(_make_face([b0, b1, t1, t0]))

    # Canopy — large rounded sphere approximation (icosphere-like, 8 faces)
    canopy_center_y = base_y + th + height * 0.35
    canopy_radius = height * 0.45

    # Create 8 triangular faces approximating a sphere
    # Top face
    top_verts = []
    for lx, lz in [(-canopy_radius * 0.7, -canopy_radius * 0.7),
                   (canopy_radius * 0.7, -canopy_radius * 0.7),
                   (canopy_radius * 0.7, canopy_radius * 0.7),
                   (-canopy_radius * 0.7, canopy_radius * 0.7)]:
        rx, rz = _rotate_y(lx, lz, ca, sa)
        top_verts.append(Vec3(wx + rx, canopy_center_y, wz + rz))

    # Apex
    apex = Vec3(wx, base_y + th + canopy_radius * 1.1, wz)

    # 4 triangular faces from base to apex
    for i in range(4):
        j = (i + 1) % 4
        faces.append(_make_face([top_verts[i], top_verts[j], apex]))

    # 4 triangular faces forming the bottom of the canopy
    bottom_apex = Vec3(wx, canopy_center_y - canopy_radius * 0.5, wz)
    for i in range(4):
        j = (i + 1) % 4
        faces.append(_make_face([top_verts[j], top_verts[i], bottom_apex]))

    return faces


def make_ground_quad(cx, cz, chunk_size):
    """Generate face data for a ground quad covering chunk (cx, cz).

    Returns 2 faces (top + bottom) so the ground is visible from both sides.
    """
    x0 = cx * chunk_size
    z0 = cz * chunk_size
    x1 = x0 + chunk_size
    z1 = z0 + chunk_size
    y = -0.02                   # slightly below y=0 to avoid z-fighting

    v0 = Vec3(x0, y, z0)
    v1 = Vec3(x1, y, z0)
    v2 = Vec3(x1, y, z1)
    v3 = Vec3(x0, y, z1)

    return [
        _make_face([v0, v1, v2, v3]),       # top    (normal +y)
        _make_face([v3, v2, v1, v0]),       # bottom (normal −y)
    ]


# ---------------------------------------------------------------------------
# Terrain height — procedural noise for hills and valleys
# ---------------------------------------------------------------------------

def _terrain_hash(ix, iz, seed):
    """Hash grid coordinates to a pseudo-random height in [0, 1]."""
    h = (seed * 1103515245 + 12345) & 0xFFFFFFFF
    h = (h ^ ((ix * 73856093) & 0xFFFFFFFF)) & 0xFFFFFFFF
    h = ((h * 1103515245 + 12345)
         ^ ((iz * 19349663) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return (h & 0xFFFF) / 0xFFFF


def terrain_height(wx, wz, seed, scale=8.0, amplitude=2.5):
    """Return terrain height at world position (wx, wz).

    Uses two octaves of smoothed value noise for rolling hills, plus a
    separate low-frequency mountain layer that produces rare, very tall
    peaks with a quadratic power curve.

    A guaranteed landmark mountain is placed near the spawn point
    (behind the camera start) so there is always a dramatic peak
    visible for reference.
    """
    total = 0.0
    for octave_scale, octave_amp in ((scale, amplitude),
                                     (scale * 0.4, amplitude * 0.25)):
        gx = wx / octave_scale
        gz = wz / octave_scale
        ix = int(math.floor(gx))
        iz = int(math.floor(gz))
        fx = gx - ix
        fz = gz - iz
        # Smoothstep interpolation
        fx = fx * fx * (3.0 - 2.0 * fx)
        fz = fz * fz * (3.0 - 2.0 * fz)
        # Bilinear interpolation of hashed corner values
        h00 = _terrain_hash(ix, iz, seed)
        h10 = _terrain_hash(ix + 1, iz, seed)
        h01 = _terrain_hash(ix, iz + 1, seed)
        h11 = _terrain_hash(ix + 1, iz + 1, seed)
        h0 = h00 + (h10 - h00) * fx
        h1 = h01 + (h11 - h01) * fx
        total += (h0 + (h1 - h0) * fz) * octave_amp

    # Mountain layer — rare, very large peaks
    mtn_scale = 70.0
    mtn_amp = 25.0
    mtn_seed = seed ^ 0xDEADBEEF
    gx = wx / mtn_scale
    gz = wz / mtn_scale
    ix = int(math.floor(gx))
    iz = int(math.floor(gz))
    fx = gx - ix
    fz = gz - iz
    fx = fx * fx * (3.0 - 2.0 * fx)
    fz = fz * fz * (3.0 - 2.0 * fz)
    h00 = _terrain_hash(ix, iz, mtn_seed)
    h10 = _terrain_hash(ix + 1, iz, mtn_seed)
    h01 = _terrain_hash(ix, iz + 1, mtn_seed)
    h11 = _terrain_hash(ix + 1, iz + 1, mtn_seed)
    h0 = h00 + (h10 - h00) * fx
    h1 = h01 + (h11 - h01) * fx
    mtn_noise = h0 + (h1 - h0) * fz
    # Threshold + cubic curve → only the highest noise peaks form mountains
    mtn_factor = max(0.0, (mtn_noise - 0.65) / 0.35)
    total += mtn_factor * mtn_factor * mtn_factor * mtn_amp

    # Guaranteed landmark mountain near spawn — a steep gaussian peak
    # behind the camera start position (cam starts at 6,_,6 facing −Z).
    # Turn around (face +Z) to see it rising above the forest.
    mtn_cx, mtn_cz = 6.0, 45.0         # 39 units behind spawn
    mtn_radius = 18.0                   # steep-ish slope
    mtn_peak = 30.0                     # very tall
    dmx = wx - mtn_cx
    dmz = wz - mtn_cz
    d2 = dmx * dmx + dmz * dmz
    cutoff = mtn_radius * 3.0           # skip math beyond 3× radius
    if d2 < cutoff * cutoff:
        total += mtn_peak * math.exp(-d2 / (2.0 * mtn_radius * mtn_radius))

    return total - amplitude * 0.3    # centre around slightly below zero


def make_terrain_grid(cx, cz, chunk_size, seed, grid_res=6):
    """Generate wireframe terrain quads for chunk (cx, cz).

    Returns a list of (verts, center, normal, edge_str) tuples.
    The 4th element marks them as wireframe-only faces for the renderer.
    """
    TERRAIN_EDGE = '\033[38;2;60;90;45m.\033[0m'

    faces = []
    cs = chunk_size
    cell = cs / grid_res
    x0 = cx * cs
    z0 = cz * cs

    # Build vertex grid (grid_res+1 × grid_res+1)
    grid = []
    for gi in range(grid_res + 1):
        row = []
        for gj in range(grid_res + 1):
            vx = x0 + gi * cell
            vz = z0 + gj * cell
            vy = terrain_height(vx, vz, seed)
            row.append(Vec3(vx, vy, vz))
        grid.append(row)

    # Generate quads
    for gi in range(grid_res):
        for gj in range(grid_res):
            v00 = grid[gi][gj]
            v10 = grid[gi + 1][gj]
            v11 = grid[gi + 1][gj + 1]
            v01 = grid[gi][gj + 1]
            face = _make_face([v00, v10, v11, v01])
            faces.append((face[0], face[1], face[2], TERRAIN_EDGE))

    return faces


def chunk_has_mountain(cx, cz, chunk_size, seed, threshold=0.70):
    """Check whether the chunk at (cx, cz) contains significant mountain terrain.

    Evaluates the mountain noise at the chunk centre — the same low-frequency
    noise used by ``terrain_height()`` — and returns ``True`` when it exceeds
    *threshold*.  Also returns ``True`` for chunks near the guaranteed
    landmark mountain at (6, 45).

    This is used to decide which distant chunks should be loaded as
    terrain-only so that mountains are visible from far away.
    """
    wx = cx * chunk_size + chunk_size * 0.5
    wz = cz * chunk_size + chunk_size * 0.5

    # Guaranteed landmark mountain near spawn (must match terrain_height())
    mtn_cx, mtn_cz = 6.0, 45.0
    mtn_radius = 18.0
    dmx = wx - mtn_cx
    dmz = wz - mtn_cz
    if dmx * dmx + dmz * dmz < (mtn_radius * 3.0) ** 2:
        return True

    mtn_seed = seed ^ 0xDEADBEEF
    mtn_scale = 70.0
    gx = wx / mtn_scale
    gz = wz / mtn_scale
    ix = int(math.floor(gx))
    iz = int(math.floor(gz))
    fx = gx - ix
    fz = gz - iz
    fx = fx * fx * (3.0 - 2.0 * fx)
    fz = fz * fz * (3.0 - 2.0 * fz)
    h00 = _terrain_hash(ix, iz, mtn_seed)
    h10 = _terrain_hash(ix + 1, iz, mtn_seed)
    h01 = _terrain_hash(ix, iz + 1, mtn_seed)
    h11 = _terrain_hash(ix + 1, iz + 1, mtn_seed)
    h0 = h00 + (h10 - h00) * fx
    h1 = h01 + (h11 - h01) * fx
    mtn_noise = h0 + (h1 - h0) * fz
    return mtn_noise > threshold


# ---------------------------------------------------------------------------
# ForestChunk — a single chunk of procedurally generated forest
# ---------------------------------------------------------------------------

class ForestChunk:
    """A square region of forest with procedurally placed objects.

    Each chunk is divided into a CELL_GRID × CELL_GRID sub-grid.  Each cell
    may contain one object chosen by weighted random selection.  The RNG is
    seeded deterministically from the world seed and chunk coordinates, so
    revisiting a location regenerates the identical layout.
    """

    CELL_GRID = 4               # 4×4 = 16 cells per chunk

    # Object type weights (cumulative selection)
    OBJ_WEIGHTS = [
        ('tree',  0.30),
        ('rock',  0.20),
        ('bush',  0.25),
        ('empty', 0.25),
    ]

    def __init__(self, cx: int, cz: int, chunk_size: float,
                 world_seed: int, terrain_only: bool = False):
        self.cx = cx
        self.cz = cz
        self.chunk_size = chunk_size
        self.terrain_only = terrain_only
        self.face_data: list = []
        self._generate(world_seed)

    # -- seeded generation ---------------------------------------------------

    @staticmethod
    def _chunk_seed(world_seed: int, cx: int, cz: int) -> int:
        h = world_seed & 0xFFFFFFFF
        h = ((h * 1103515245 + 12345)
             ^ ((cx * 73856093) & 0xFFFFFFFF)) & 0xFFFFFFFF
        h = ((h * 1103515245 + 12345)
             ^ ((cz * 19349663) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return h

    def _generate(self, world_seed: int):
        rng = random.Random(
            self._chunk_seed(world_seed, self.cx, self.cz))
        cs = self.chunk_size
        cell_size = cs / self.CELL_GRID

        # Skip object placement for terrain-only chunks (distant mountains).
        # Use a coarser grid (3×3 instead of 6×6) since fine detail isn't
        # visible at long range — reduces face count by 75%.
        if self.terrain_only:
            self.face_data.extend(
                make_terrain_grid(self.cx, self.cz, cs, world_seed,
                                  grid_res=3))
            return

        # Place objects in each cell
        for gi in range(self.CELL_GRID):
            for gj in range(self.CELL_GRID):
                # Cell centre in world space
                cell_cx = self.cx * cs + (gi + 0.5) * cell_size
                cell_cz = self.cz * cs + (gj + 0.5) * cell_size

                # Weighted random object type
                roll = rng.random()
                cumulative = 0.0
                obj_type = 'empty'
                for otype, weight in self.OBJ_WEIGHTS:
                    cumulative += weight
                    if roll < cumulative:
                        obj_type = otype
                        break

                if obj_type == 'empty':
                    continue

                # Jitter position within cell
                jx = (rng.random() - 0.5) * cell_size * 0.7
                jz = (rng.random() - 0.5) * cell_size * 0.7
                wx = cell_cx + jx
                wz = cell_cz + jz

                # Random rotation
                angle = rng.random() * math.pi * 2

                # Terrain height at object position
                by = terrain_height(wx, wz, world_seed)

                if obj_type == 'tree':
                    height = 1.8 + rng.random() * 1.5   # 1.8–3.3
                    self.face_data.extend(
                        make_pine_tree(wx, wz, height, angle, rng,
                                       base_y=by))
                elif obj_type == 'rock':
                    scale = 0.25 + rng.random() * 0.4   # 0.25–0.65
                    self.face_data.extend(
                        make_rock(wx, wz, scale, angle, rng,
                                  base_y=by))
                elif obj_type == 'bush':
                    scale = 0.4 + rng.random() * 0.3    # 0.4–0.7
                    self.face_data.extend(
                        make_bush(wx, wz, scale, angle, rng,
                                  base_y=by))

        # Generate terrain wireframe grid
        self.face_data.extend(
            make_terrain_grid(self.cx, self.cz, cs, world_seed))


# ---------------------------------------------------------------------------
# ForestWorld — infinite procedural forest with chunk streaming
# ---------------------------------------------------------------------------

class ForestWorld:
    """Manages an infinite procedural forest via chunk-based streaming.

    Implements ``get_face_data()`` compatible with the Renderer, so it can
    be passed in place of a ``Model``.
    """

    def __init__(self, seed: int = 42, chunk_size: float = 12.0,
                 render_distance: int = 2):
        self.seed = seed
        self.chunk_size = chunk_size
        self.render_distance = render_distance
        self.chunks: dict = {}          # (cx, cz) → ForestChunk
        self._cam_forward = Vec3(0, 0, -1)
        self._cam_pos = Vec3(0, 0, 0)
        self._last_face_count = 0       # for status-bar diagnostics
        self._last_mtn_chunks = 0       # mountain chunks loaded (diagnostics)
        self._mtn_cache: dict = {}      # (cx, cz) → bool — mountain noise cache
        
        # Special tree (golden oak) — spawns at random location ~10 sec walk from spawn
        self.special_tree_pos = None    # (wx, wz, base_y) or None
        self.special_tree_face_data = None  # pre-computed face data
        self.spawn_pos = Vec3(6.0, 0.0, 6.0)  # player spawn position
        self._special_tree_spawned = False

    # -- chunk loading / unloading ------------------------------------------

    def _spawn_special_tree(self):
        """Spawn the special golden oak tree at a random location ~10 sec walk from spawn."""
        if self._special_tree_spawned:
            return
        
        # Use a seeded RNG for deterministic spawn position based on world seed
        rng = random.Random(self.seed + 999999)
        
        # Distance: Very close to spawn for immediate visibility
        distance = 5.0 + rng.random() * 3.0  # 5-8 units (very close)
        
        # Random angle
        angle = rng.random() * math.pi * 2
        
        # Calculate position
        wx = self.spawn_pos.x + distance * math.sin(angle)
        wz = self.spawn_pos.z + distance * math.cos(angle)
        
        # Get terrain height at this position
        base_y = terrain_height(wx, wz, self.seed)
        
        # Store position
        self.special_tree_pos = (wx, wz, base_y)
        
        # Generate oak tree with fixed height and random rotation
        height = 3.5 + rng.random() * 0.5  # 3.5-4.0 units
        tree_angle = rng.random() * math.pi * 2
        
        # Generate face data
        self.special_tree_face_data = make_oak_tree(wx, wz, height, tree_angle, rng, base_y)
        
        self._special_tree_spawned = True

    def update(self, camera: 'Camera'):
        """Load / unload chunks based on camera position.

        Three loading tiers:
          1. Full detail (objects + terrain) within render_distance
          2. Intermediate terrain-only within terrain_rd — fills the visual
             gap between nearby geometry and distant mountains so the ground
             connects seamlessly and mountains don't appear to float.
          3. Mountain-only terrain beyond terrain_rd where chunk_has_mountain()
             is true — renders distant peak silhouettes.
        """
        # Spawn special tree on first update
        self._spawn_special_tree()
        
        self._cam_pos = camera.position
        self._cam_forward = camera.forward

        cs = self.chunk_size
        cam_cx = int(math.floor(camera.position.x / cs))
        cam_cz = int(math.floor(camera.position.z / cs))
        rd = self.render_distance

        # ── Tier 1: normal chunks (full detail) ──────────────────────────
        needed = set()
        for dx in range(-rd, rd + 1):
            for dz in range(-rd, rd + 1):
                needed.add((cam_cx + dx, cam_cz + dz))

        # Mountain scan radius (used by tiers 2 and 3)
        mtn_rd = max(16, rd * 3)

        # ── Tier 2: intermediate terrain-only chunks ─────────────────────
        # Fills the gap between nearby detail and distant mountains so
        # the ground is visible all the way to the horizon.  Capped to
        # keep chunk count manageable (scales up on mountaintops where
        # dynamic rd increases).
        terrain_rd = max(8, rd * 3)
        terrain_needed = set()
        for dx in range(-terrain_rd, terrain_rd + 1):
            for dz in range(-terrain_rd, terrain_rd + 1):
                key = (cam_cx + dx, cam_cz + dz)
                if key not in needed:
                    terrain_needed.add(key)

        # ── Tier 3: extended mountain chunks (terrain wireframe only) ────
        # Scan a much wider radius; only load chunks that contain mountain
        # noise so their silhouettes are visible from far away.
        mtn_needed = set()
        mtn_cache = self._mtn_cache
        for dx in range(-mtn_rd, mtn_rd + 1):
            for dz in range(-mtn_rd, mtn_rd + 1):
                key = (cam_cx + dx, cam_cz + dz)
                if key in needed or key in terrain_needed:
                    continue        # already covered by tier 1 or 2
                if key not in mtn_cache:
                    mtn_cache[key] = chunk_has_mountain(
                        key[0], key[1], cs, self.seed)
                if mtn_cache[key]:
                    mtn_needed.add(key)
        self._last_mtn_chunks = len(mtn_needed)

        all_needed = needed | terrain_needed | mtn_needed

        # Unload chunks that are no longer in any tier
        to_remove = [k for k in self.chunks if k not in all_needed]
        for k in to_remove:
            del self.chunks[k]

        # Load new chunks (limit per frame to avoid stutter; higher when
        # render distance is large, e.g. viewing from a mountaintop)
        max_load = 2 if rd <= 3 else 4
        loaded = 0

        # Prioritise normal full-detail chunks
        for key in needed:
            if key not in self.chunks:
                self.chunks[key] = ForestChunk(
                    key[0], key[1], cs, self.seed)
                loaded += 1
                if loaded >= max_load:
                    break

        # Then load intermediate terrain-only chunks (cheap, coarse grid).
        terrain_loaded = 0
        terrain_max = 8
        for key in terrain_needed:
            if key not in self.chunks:
                self.chunks[key] = ForestChunk(
                    key[0], key[1], cs, self.seed, terrain_only=True)
                terrain_loaded += 1
                if terrain_loaded >= terrain_max:
                    break

        # Then load distant mountain chunks (terrain-only).
        # These are much cheaper to generate (no objects), so allow a
        # higher per-frame budget so mountains appear quickly.
        mtn_loaded = 0
        mtn_max = 8
        for key in mtn_needed:
            if key not in self.chunks:
                self.chunks[key] = ForestChunk(
                    key[0], key[1], cs, self.seed, terrain_only=True)
                mtn_loaded += 1
                if mtn_loaded >= mtn_max:
                    break

    # -- face data for the renderer -----------------------------------------

    def get_face_data(self) -> list:
        """Return face data for all visible chunks plus special tree and path.

        Applies two culling passes:
          1. Behind-camera: chunks whose centre is behind the camera are
             skipped entirely (generous margin for chunk size).
          2. Distance: terrain-only (distant mountain) chunks beyond a max
             render distance are skipped to avoid sub-pixel wireframe work.
        """
        result = []
        cs = self.chunk_size
        cam_px = self._cam_pos.x
        cam_pz = self._cam_pos.z
        fwd_x = self._cam_forward.x
        fwd_z = self._cam_forward.z
        # Mountain chunks beyond this distance² are culled from rendering
        # (they're loaded for pop-in prevention but too far for wireframe)
        mtn_render_dist = cs * 10.0     # ~120 world units
        mtn_dist_sq = mtn_render_dist * mtn_render_dist

        for (cx, cz), chunk in self.chunks.items():
            # Chunk centre in world space
            ccx = cx * cs + cs * 0.5
            ccz = cz * cs + cs * 0.5

            # Vector from camera to chunk centre
            dx = ccx - cam_px
            dz = ccz - cam_pz

            # Dot product with camera forward (XZ only)
            dot_fwd = dx * fwd_x + dz * fwd_z

            # Skip chunks entirely behind camera (generous margin)
            if dot_fwd < -cs * 1.5:
                continue

            # Terrain-only mountain chunks: cull if too far for wireframe
            if chunk.terrain_only:
                if dx * dx + dz * dz > mtn_dist_sq:
                    continue

            result.extend(chunk.face_data)

        # Add yellow path from spawn to special tree
        if self.special_tree_pos is not None and self._special_tree_spawned:
            wx, wz, base_y = self.special_tree_pos
            spawn_x, spawn_y, spawn_z = self.spawn_pos.x, self.spawn_pos.y, self.spawn_pos.z
            
            # Generate path as a series of small markers along the path
            path_length = math.sqrt((wx - spawn_x)**2 + (wz - spawn_z)**2)
            num_markers = int(path_length / 1.5)  # One marker every 1.5 units for denser path
            
            # Yellow edge color for path markers - bright golden yellow
            PATH_EDGE = '\033[38;2;255;255;0m#\033[0m'  # Bright yellow (#FFFF00)
            
            for i in range(num_markers + 1):
                t = i / max(num_markers, 1)
                px = spawn_x + t * (wx - spawn_x)
                pz = spawn_z + t * (wz - spawn_z)
                py = terrain_height(px, pz, self.seed) + 0.01
                
                # Diamond shape marker on ground - larger for visibility
                marker_size = 0.6
                v0 = Vec3(px, py, pz - marker_size)
                v1 = Vec3(px + marker_size, py, pz)
                v2 = Vec3(px, py, pz + marker_size)
                v3 = Vec3(px - marker_size, py, pz)
                
                # Create quad face WITH yellow wireframe marker
                face = _make_face([v0, v1, v2, v3])
                # Add 4th element with yellow edge - wireframe-only rendering
                result.append((face[0], face[1], face[2], PATH_EDGE))

        # Add special tree (golden oak) - rendered as filled faces (no wireframe marker)
        if self.special_tree_face_data is not None:
            result.extend(self.special_tree_face_data)

        self._last_face_count = len(result)
        return result

    # -- compatibility shims ------------------------------------------------

    def bounding_radius(self) -> float:
        """Dummy bounding radius for Renderer auto-fit compatibility."""
        return self.chunk_size * self.render_distance


# ---------------------------------------------------------------------------
# Non-blocking keyboard input
# ---------------------------------------------------------------------------

class KeyboardInput:
    """Non-blocking keyboard input for Unix terminals (requires termios)."""

    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)
        new = termios.tcgetattr(self.fd)
        # Disable canonical mode and echo; keep signal generation (ISIG)
        new[3] = new[3] & ~(termios.ICANON | termios.ECHO)
        new[6][termios.VMIN] = 0
        new[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSADRAIN, new)

    def get_keys(self) -> list:
        """Return a list of key names for all pending keypresses."""
        keys = []
        try:
            while select.select([sys.stdin], [], [], 0)[0]:
                ch = os.read(self.fd, 1)
                if not ch:
                    break
                b = ch[0]
                if b == 0x1B:  # ESC — possible arrow-key sequence
                    if select.select([sys.stdin], [], [], 0.02)[0]:
                        ch2 = os.read(self.fd, 1)
                        if ch2 and ch2[0] == 0x5B:   # '['
                            if select.select([sys.stdin], [], [], 0.02)[0]:
                                ch3 = os.read(self.fd, 1)
                                if ch3:
                                    m = {65: 'UP', 66: 'DOWN',
                                         67: 'RIGHT', 68: 'LEFT'}
                                    if ch3[0] in m:
                                        keys.append(m[ch3[0]])
                                    continue
                    keys.append('ESC')
                elif b == 0x09:
                    keys.append('TAB')
                elif b == 0x20:
                    keys.append('SPACE')
                else:
                    try:
                        keys.append(ch.decode('utf-8'))
                    except UnicodeDecodeError:
                        pass
        except (OSError, InterruptedError):
            pass
        return keys

    def restore(self):
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)


# ---------------------------------------------------------------------------
# Renderer — supports orthographic (spin) and perspective (movement) modes
# ---------------------------------------------------------------------------

class Renderer:
    """ASCII renderer for any 3D Model with per-pixel point-light shading.

    Two rendering paths:
      • _render_ortho       — original orthographic projection (spin mode)
      • _render_perspective  — perspective projection via Camera (move mode)
    """

    SHADING = '.:-=+*%@'
    CHAR_ASPECT = 2.0
    EDGE_STR = '\033[38;2;159;239;0m#\033[0m'

    def __init__(self, width: int, height: int, model=None):
        self.width = width
        self.height = height
        # Auto-fit: scale so the model's bounding sphere fits the viewport
        if model is not None:
            max_extent = model.bounding_radius()
            self.scale = min(
                (width // 2 - 1) / max_extent,
                (height // 2 - 1) * self.CHAR_ASPECT / max_extent,
            )
        else:
            self.scale = 1.0
        # Perspective parameters (for movement mode)
        self.near_plane = 0.01
        self._fov_deg = 90.0              # default; overridden by set_fov()
        self.focal = width * 0.8          # recalculated by set_fov()
        self.draw_edges = True            # toggle wireframe edges
        self.fog_distance = 0.0           # 0 = no fog; >0 = fade starts here

    def set_fov(self, fov_degrees: float):
        """Set the horizontal field of view (degrees) for perspective mode."""
        self._fov_deg = fov_degrees
        half_fov_rad = math.radians(fov_degrees * 0.5)
        self.focal = (self.width * 0.5) / math.tan(half_fov_rad)
        self.light_pos = Vec3(3.0, 4.0, 3.0)
        self.ambient = 0.12

    # ── public entry point ─────────────────────────────────────────────────

    def render(self, model: Model, camera: 'Camera | None' = None) -> list:
        """Render *model* into a 2-D char buffer.

        If *camera* is ``None``, use the original orthographic path.
        Otherwise use perspective projection through *camera*.
        """
        if camera is not None:
            return self._render_perspective(model, camera)
        return self._render_ortho(model)

    # ── orthographic path (original) ───────────────────────────────────────

    def _project_vertex_ortho(self, v: Vec3) -> 'tuple | None':
        """Orthographic projection → (screen_x, screen_y) or None."""
        x = round(v.x * self.scale + self.width // 2)
        y = round(-v.y * self.scale / self.CHAR_ASPECT + self.height // 2)
        margin = max(self.width, self.height)
        if -margin <= x < self.width + margin and -margin <= y < self.height + margin:
            return (x, y)
        return None

    def _render_ortho(self, model: Model) -> list:
        """Render with orthographic projection (spin mode)."""
        visible = []
        for vs, center, normal in model.get_face_data():
            if normal.z > 0:
                visible.append((vs, center, normal))

        buffer = [[' '] * self.width for _ in range(self.height)]
        zbuffer = [[-1e30] * self.width for _ in range(self.height)]

        for vs, center, normal in visible:
            projected = [self._project_vertex_ortho(v) for v in vs]
            if all(projected):
                self._draw_face_lit_ortho(buffer, zbuffer, projected,
                                          vs[0], normal)

        for vs, center, normal in visible:
            projected = [self._project_vertex_ortho(v) for v in vs]
            if all(projected):
                n = len(projected)
                for i in range(n):
                    j = (i + 1) % n
                    self._draw_line(buffer, zbuffer,
                                    projected[i], projected[j],
                                    vs[i].z, vs[j].z,
                                    self.EDGE_STR, z_bias=0.005)
        return buffer

    def _draw_face_lit_ortho(self, buffer, zbuffer, projected, v0, normal):
        """Fill a convex polygon with per-pixel z-buffered point-light shading
        (orthographic projection)."""
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

    # ── perspective path (movement mode) ───────────────────────────────────

    @staticmethod
    def _clip_polygon_near(cam_vs: list, near: float) -> list:
        """Sutherland-Hodgman clip of a camera-space polygon against the near
        plane (cam_z = *near*).

        Returns a new list of (cx, cy, cz) tuples representing the clipped
        polygon, which may have more vertices than the input (up to +1 per
        original edge).  Returns an empty list when the polygon is entirely
        behind the near plane.
        """
        out = []
        n = len(cam_vs)
        for i in range(n):
            cur = cam_vs[i]
            nxt = cam_vs[(i + 1) % n]
            cur_in = cur[2] > near
            nxt_in = nxt[2] > near
            if cur_in:
                out.append(cur)
                if not nxt_in:          # edge exits: emit intersection
                    t = (near - cur[2]) / (nxt[2] - cur[2])
                    out.append((
                        cur[0] + t * (nxt[0] - cur[0]),
                        cur[1] + t * (nxt[1] - cur[1]),
                        near,
                    ))
            elif nxt_in:                # edge enters: emit intersection
                t = (near - cur[2]) / (nxt[2] - cur[2])
                out.append((
                    cur[0] + t * (nxt[0] - cur[0]),
                    cur[1] + t * (nxt[1] - cur[1]),
                    near,
                ))
        return out

    def _project_vertex_persp(self, cam_v: tuple) -> 'tuple | None':
        """Perspective projection of a camera-space vertex → (sx, sy) or None.

        After near-plane clipping, vertices at cam_z ≈ near can project to
        extreme screen coordinates.  Instead of rejecting them (which would
        discard the entire face), we clamp to a generous range.  The fill
        loop already clamps its bounding box to screen bounds, so large
        off-screen coordinates are harmless — we just cap them to limit
        Bresenham edge-drawing cost.
        """
        cx, cy, cz = cam_v
        if cz <= self.near_plane:
            return None
        x = round(self.focal * cx / cz + self.width // 2)
        y = round(-self.focal * cy / (cz * self.CHAR_ASPECT) + self.height // 2)
        # Clamp (not reject) to keep faces visible when partially off-screen
        LIMIT = max(self.width, self.height) * 10
        x = max(-LIMIT, min(LIMIT, x))
        y = max(-LIMIT, min(LIMIT, y))
        return (x, y)

    def _render_perspective(self, model: Model, camera: Camera) -> list:
        """Render with perspective projection through *camera*.

        Performance optimisations over the naive approach:
          • Camera matrix extracted once; view_transform / transform_direction
            inlined to eliminate per-vertex method-dispatch overhead.
          • Vertices projected once and stored — reused by both the fill and
            edge passes (previously every face was projected twice).
          • Fog-faded edge ANSI strings cached by quantised fog level so
            identical strings are shared across hundreds of terrain faces.
        """
        near = self.near_plane

        # ── Extract camera matrix once (avoids method dispatch per vertex)
        crx, cry, crz = camera.right.x, camera.right.y, camera.right.z
        cux, cuy, cuz = camera.up.x, camera.up.y, camera.up.z
        cfx, cfy, cfz = camera.forward.x, camera.forward.y, camera.forward.z
        cpx, cpy, cpz = camera.position.x, camera.position.y, camera.position.z

        # Transform the light into camera space (once per frame) — inlined
        dlx = self.light_pos.x - cpx
        dly = self.light_pos.y - cpy
        dlz = self.light_pos.z - cpz
        light_cam = (crx * dlx + cry * dly + crz * dlz,
                     cux * dlx + cuy * dly + cuz * dlz,
                     cfx * dlx + cfy * dly + cfz * dlz)

        # ── Gather visible faces ─────────────────────────────────────────
        # Each entry now includes pre-computed projection to avoid re-work.
        visible = []
        _clip = self._clip_polygon_near
        _proj = self._project_vertex_persp

        for item in model.get_face_data():
            vs = item[0]
            normal = item[2]
            wireframe = item[3] if len(item) > 3 else None
            world_y = item[1].y

            # Inline view_transform — replaces camera.view_transform() calls
            cam_vs = []
            any_in_front = False
            for v in vs:
                dx = v.x - cpx
                dy = v.y - cpy
                dz = v.z - cpz
                cz = cfx * dx + cfy * dy + cfz * dz
                if cz > near:
                    any_in_front = True
                cam_vs.append((crx * dx + cry * dy + crz * dz,
                               cux * dx + cuy * dy + cuz * dz,
                               cz))

            if not any_in_front:
                continue

            clipped = _clip(cam_vs, near)
            if len(clipped) < 3:
                continue

            # Inline transform_direction for normal
            nx, ny, nz = normal.x, normal.y, normal.z
            cam_n = (crx * nx + cry * ny + crz * nz,
                     cux * nx + cuy * ny + cuz * nz,
                     cfx * nx + cfy * ny + cfz * nz)

            # Project once — reused by both fill and edge passes
            projected = [_proj(cv) for cv in clipped]
            if not all(projected):
                continue

            visible.append((clipped, cam_n, wireframe, world_y, projected))

        # ── Draw ─────────────────────────────────────────────────────────
        buffer = [[' '] * self.width for _ in range(self.height)]
        zbuffer = [[-1e30] * self.width for _ in range(self.height)]

        # Filled faces (skip wireframe-only faces)
        for cam_vs, cam_n, wireframe, world_y, projected in visible:
            if wireframe is not None:
                continue
            self._draw_face_lit_persp(buffer, zbuffer, projected,
                                      cam_vs[0], cam_n, light_cam,
                                      world_y)

        # Edges — always draw wireframe faces; filled-face edges if draw_edges.
        fog_dist = self.fog_distance
        draw_edges = self.draw_edges
        _draw_line = self._draw_line
        edge_cache = {}       # (is_wire, quantised_fade) → ANSI string

        for cam_vs, cam_n, wireframe, world_y, projected in visible:
            if wireframe is None and not draw_edges:
                continue

            # Fog fade
            if fog_dist > 0:
                n_cv = len(cam_vs)
                tot_z = 0.0
                for cv in cam_vs:
                    tot_z += cv[2]
                fog = min(1.0, (tot_z / n_cv) / fog_dist)

                if wireframe is not None and world_y > 4.0:
                    alt = min(1.0, (world_y - 4.0) / 15.0)
                    fog_eff = fog * (1.0 - alt * 0.92)
                else:
                    fog_eff = fog

                fog_fade = max(0.0, 1.0 - fog_eff * fog_eff)
                if fog_fade < 0.03:
                    continue
            else:
                fog_fade = 1.0

            # Quantised edge-string cache (21 levels per type, shared across
            # hundreds of terrain faces to avoid per-face f-string allocation)
            is_wire = wireframe is not None
            
            # If wireframe marker is provided (like yellow path), use it directly
            # Only apply fog fade to terrain wireframe (not special markers)
            if is_wire and wireframe != '\033[38;2;60;90;45m.\033[0m':
                # Special wireframe marker (e.g., yellow path) - preserve original color
                edge_str = wireframe
            else:
                q = int(fog_fade * 20)
                cache_key = (is_wire, q)
                edge_str = edge_cache.get(cache_key)
                if edge_str is None:
                    ff = q * 0.05
                    if is_wire:
                        edge_str = f'\033[38;2;{int(60*ff)};{int(90*ff)};{int(45*ff)}m.\033[0m'
                    else:
                        edge_str = f'\033[38;2;{int(159*ff)};{int(239*ff)};0m#\033[0m'
                    edge_cache[cache_key] = edge_str

            z_bias = 0.0 if is_wire else 0.005
            nv = len(projected)
            for i in range(nv):
                j = (i + 1) % nv
                _draw_line(buffer, zbuffer,
                           projected[i], projected[j],
                           -cam_vs[i][2], -cam_vs[j][2],
                           edge_str, z_bias=z_bias)
        return buffer

    def _draw_face_lit_persp(self, buffer, zbuffer, projected,
                             cam_v0, cam_normal, light_cam,
                             world_y=0.0):
        """Scanline-fill a convex polygon with perspective-correct lighting.

        Uses edge-intersection scanline traversal instead of bounding-box +
        point-in-polygon, eliminating the per-pixel polygon test.  For a
        typical 3–5 vertex face this is 3–7× faster in the fill pass.

        All coordinates are in **camera space**.
        Depth stored as ``-cam_z`` (higher = closer).
        """
        n_verts = len(projected)

        # ── Screen-space Y bounds ────────────────────────────────────────
        ymin_v = ymax_v = projected[0][1]
        for i in range(1, n_verts):
            py = projected[i][1]
            if py < ymin_v:
                ymin_v = py
            elif py > ymax_v:
                ymax_v = py

        width = self.width
        height_m1 = self.height - 1
        ymin = ymin_v if ymin_v > 0 else 0
        ymax = ymax_v if ymax_v < height_m1 else height_m1
        if ymin > ymax:
            return

        # ── Pre-compute constants ────────────────────────────────────────
        scx = width >> 1
        scy = self.height >> 1
        focal = self.focal
        inv_focal = 1.0 / focal
        char_aspect = self.CHAR_ASPECT

        cnx, cny, cnz = cam_normal
        cv0x, cv0y, cv0z = cam_v0
        d = cnx * cv0x + cny * cv0y + cnz * cv0z

        lcx, lcy, lcz = light_cam
        shading = self.SHADING
        num_shades = len(shading) - 1
        ambient = self.ambient
        _sqrt = math.sqrt
        near = self.near_plane
        fog_dist = self.fog_distance
        fog_height_factor = 1.0

        # ── Build edge table (non-horizontal edges, sorted top→bottom) ──
        edges = []
        for i in range(n_verts):
            j = (i + 1) % n_verts
            x0, y0 = projected[i]
            x1, y1 = projected[j]
            if y0 == y1:
                continue
            if y0 > y1:
                x0, y0, x1, y1 = x1, y1, x0, y0
            edges.append((x0, y0, x1, y1, (x1 - x0) / (y1 - y0)))

        # ── Scanline fill ────────────────────────────────────────────────
        for y in range(ymin, ymax + 1):
            x_left = 1e9
            x_right = -1e9

            for ex0, ey0, ex1, ey1, slope in edges:
                if ey0 <= y <= ey1:
                    ix = ex0 + (y - ey0) * slope
                    if ix < x_left:
                        x_left = ix
                    if ix > x_right:
                        x_right = ix

            # Include vertices exactly at this scanline (handles tips)
            for i in range(n_verts):
                if projected[i][1] == y:
                    vx = projected[i][0]
                    if vx < x_left:
                        x_left = vx
                    if vx > x_right:
                        x_right = vx

            xl = int(x_left) if x_left >= 0 else 0
            if xl < 0:
                xl = 0
            xr = int(x_right)
            if xr > width - 1:
                xr = width - 1
            if xl > xr:
                continue

            ry = -(y - scy) * char_aspect * inv_focal
            buf_row = buffer[y]
            zbuf_row = zbuffer[y]

            for x in range(xl, xr + 1):
                rx = (x - scx) * inv_focal

                denom = cnx * rx + cny * ry + cnz
                if abs(denom) < 1e-10:
                    continue
                cam_z = d / denom
                if cam_z <= near:
                    continue

                zbuf_z = -cam_z
                if zbuf_z < zbuf_row[x]:
                    continue
                zbuf_row[x] = zbuf_z

                cam_x = rx * cam_z
                cam_y = ry * cam_z

                dlx = lcx - cam_x
                dly = lcy - cam_y
                dlz = lcz - cam_z
                dist = _sqrt(dlx * dlx + dly * dly + dlz * dlz)
                if dist > 0:
                    inv_d = 1.0 / dist
                    diffuse = max(0.0, cnx * dlx * inv_d
                                   + cny * dly * inv_d
                                   + cnz * dlz * inv_d)
                    atten = 1.0 / (1.0 + 0.02 * dist * dist)
                    brightness = ambient + (1.0 - ambient) * diffuse * atten
                else:
                    brightness = 1.0

                if fog_dist > 0:
                    fog = min(1.0, cam_z / fog_dist) * fog_height_factor
                    brightness *= (1.0 - fog * fog)

                idx = int(brightness * num_shades)
                if idx <= 0 and fog_dist > 0:
                    continue
                buf_row[x] = shading[max(0, min(num_shades, idx))]

    # ── shared helpers ─────────────────────────────────────────────────────

    def _draw_line(self, buffer, zbuffer, p1, p2, z1, z2, char, z_bias=0.0):
        """Bresenham line with per-pixel z-buffer depth test.

        Uses incremental z instead of per-step division for speed.
        """
        x1, y1 = p1
        x2, y2 = p2
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        total = max(dx, dy)
        z = z1 + z_bias
        z_inc = (z2 - z1) / total if total > 0 else 0.0
        w = self.width
        h = self.height
        while True:
            if 0 <= x1 < w and 0 <= y1 < h:
                zbuf_row = zbuffer[y1]
                if z >= zbuf_row[x1]:
                    zbuf_row[x1] = z
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
            z += z_inc

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
    """Main application class — works with any Model.

    Supports two interactive modes:
      • ``rotate``  — model auto-spins (original behaviour)
      • ``move``    — free-camera navigation with perspective projection
    """

    def __init__(self, args):
        self.args = args
        self.forest_mode = getattr(args, 'forest', False)
        self.running = True
        self.keyboard = None

        if self.forest_mode:
            # Forest mode — infinite procedural world
            self._base_render_dist = getattr(args, 'render_dist', 2)
            self.world = ForestWorld(
                seed=getattr(args, 'seed', 42),
                chunk_size=12.0,
                render_distance=self._base_render_dist,
            )
            self.model = None
            self.renderer = Renderer(args.width, args.height)
            self.renderer.set_fov(getattr(args, 'fov', 90.0))
            self.renderer.fog_distance = 12.0 * self._base_render_dist
            self.mode = 'move'

            # Camera at eye level
            self.camera = Camera(position=Vec3(6.0, 1.5, 6.0))
            self.move_speed = 0.15
            self.turn_speed = 0.05
        else:
            # Static model mode (original behaviour)
            model_cls = MODELS[args.model]
            self.model = model_cls(args.size)
            self.world = None
            self.renderer = Renderer(args.width, args.height, self.model)
            self.renderer.set_fov(getattr(args, 'fov', 90.0))
            self.mode = 'move' if getattr(args, 'move', False) else 'rotate'

            # Camera for movement mode — start far enough back to see the model
            radius = self.model.bounding_radius()
            self.camera = Camera(
                position=Vec3(0.0, radius * 0.3, radius * 3.0))

            # Speeds (scale to model size for consistent feel)
            self.move_speed = radius * 0.06
            self.turn_speed = 0.05

        # Key-state tracking for smooth held-key movement
        # (bridges the terminal typematic delay so holding a key moves
        #  continuously from the first press without the OS repeat-delay gap)
        self._key_state = {}        # key name → last-press timestamp
        self._key_timeout = 0.25    # seconds before a key is considered released

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        self.running = False

    # -- keyboard setup / teardown ------------------------------------------

    def _setup_keyboard(self):
        if HAS_TERMIOS:
            self.keyboard = KeyboardInput()

    def _teardown_keyboard(self):
        if self.keyboard:
            self.keyboard.restore()
            self.keyboard = None

    # -- input handling -----------------------------------------------------

    def _handle_input(self):
        if not self.keyboard:
            return
        now = time.time()
        got_input = False
        for key in self.keyboard.get_keys():
            # Global keys (instant, not state-tracked)
            if key in ('q', 'Q', '\x03'):
                self.running = False
                return
            if key in ('TAB', 'm', 'M'):
                if not self.forest_mode:
                    self.mode = 'move' if self.mode == 'rotate' else 'rotate'
                continue
            # Record timestamp for key-state tracking
            self._key_state[key] = now
            got_input = True

        # While the terminal is sending us ANY input, keep all recently-held
        # keys alive.  Terminal typematic repeat only repeats the last key
        # pressed, so when a second key starts repeating, the first key's
        # events stop — even though the user is still physically holding it.
        # By refreshing all active timestamps on any input, we bridge this
        # gap: keys only expire after ALL input stops for _key_timeout.
        if got_input:
            for k in self._key_state:
                if now - self._key_state[k] < self._key_timeout:
                    self._key_state[k] = now

        # Apply movement for all currently-held keys (movement mode only).
        # A key is considered "held" if it was pressed within the timeout
        # window — this bridges the OS typematic delay so that holding a
        # key gives smooth, immediate continuous movement.
        if self.mode == 'move':
            held = {k for k, t in self._key_state.items()
                    if now - t < self._key_timeout}
            if held & {'UP', 'w', 'W'}:
                self.camera.move_forward(self.move_speed)
            if held & {'DOWN', 's', 'S'}:
                self.camera.move_forward(-self.move_speed)
            if 'LEFT' in held:
                self.camera.turn(-self.turn_speed)
            if 'RIGHT' in held:
                self.camera.turn(self.turn_speed)
            if held & {'a', 'A'}:
                self.camera.move_right(-self.move_speed)
            if held & {'d', 'D'}:
                self.camera.move_right(self.move_speed)
            if held & {'r', 'R', 'SPACE'}:
                self.camera.move_up(self.move_speed)
            if held & {'f', 'F'}:
                self.camera.move_up(-self.move_speed)
            if held & {'e', 'E'}:
                self.camera.turn(0, self.turn_speed)
            if held & {'c', 'C'}:
                self.camera.turn(0, -self.turn_speed)

    # -- update & render ----------------------------------------------------

    def update(self):
        self._handle_input()
        if self.forest_mode:
            # Track terrain height — camera walks over hills and valleys
            cp = self.camera.position
            ty = terrain_height(cp.x, cp.z, self.world.seed)
            cp.y = ty + 1.5          # eye height above terrain surface

            # Dynamic render distance — see further from mountaintops
            base_rd = self._base_render_dist
            extra_rd = min(4, int(cp.y / 4.0))
            effective_rd = base_rd + max(0, extra_rd)
            if effective_rd != self.world.render_distance:
                self.world.render_distance = effective_rd
                self.renderer.fog_distance = 12.0 * effective_rd

            self.world.update(self.camera)
            # Move light with camera for consistent forest illumination
            self.renderer.light_pos = Vec3(cp.x + 5, cp.y + 20, cp.z + 5)
        elif self.mode == 'rotate':
            self.model.rotate(
                self.args.speed_x,
                self.args.speed_y,
                self.args.speed_z if self.args.rotate_z else 0,
            )

    def render(self):
        if self.forest_mode:
            buffer = self.renderer.render(self.world, camera=self.camera)
        elif self.mode == 'move':
            buffer = self.renderer.render(self.model, camera=self.camera)
        else:
            buffer = self.renderer.render(self.model)

        # Build status bar
        if self.forest_mode:
            fc = self.world._last_face_count
            nc = len(self.world.chunks)
            mc = self.world._last_mtn_chunks
            px = self.camera.position.x
            py = self.camera.position.y
            pz = self.camera.position.z
            status = (f"\033[7m FOREST \033[0m "
                      f"WASD=move Arrows=turn E/C=pitch "
                      f"Chunks:{nc}(mtn:{mc}) Faces:{fc} "
                      f"Pos:({px:.0f},{py:.1f},{pz:.0f}) Q=quit")
        elif self.mode == 'move':
            status = ("\033[7m MOVE \033[0m "
                      "WASD=move Arrows=turn R/F=up/dn E/C=pitch "
                      "Tab=spin Q=quit")
        else:
            status = "\033[7m SPIN \033[0m Tab=move Q=quit"

        out = '\033[H'                  # cursor home (no full clear → less flicker)
        out += self.renderer.buffer_to_string(buffer)
        out += '\n' + status + '\033[K'  # \033[K = clear to end of line
        sys.stdout.write(out)
        sys.stdout.flush()

    def run(self):
        self._setup_keyboard()
        # Hide cursor for cleaner display
        sys.stdout.write('\033[2J\033[H\033[?25l')
        sys.stdout.flush()
        try:
            frame_time = 1.0 / self.args.fps
            while self.running:
                start = time.time()
                self.update()
                self.render()
                time.sleep(max(0, frame_time - (time.time() - start)))
        finally:
            self._teardown_keyboard()
            # Show cursor and clear screen on exit
            sys.stdout.write('\033[?25h\033[2J\033[H')
            sys.stdout.flush()


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
    parser.add_argument('--move', action='store_true',
                        help='Start in movement mode (free camera navigation)')
    parser.add_argument('--fov', type=float, default=90.0,
                        help='Horizontal field of view in degrees (default: 90)')
    parser.add_argument('--forest', action='store_true',
                        help='Start in infinite procedural forest mode')
    parser.add_argument('--seed', type=int, default=42,
                        help='World seed for forest generation (default: 42)')
    parser.add_argument('--render-dist', type=int, default=2,
                        help='Chunk render distance for forest (default: 2)')
    parser.add_argument('--frame', '-fr', type=int, default=None,
                        help='Render a specific frame and exit')

    args = parser.parse_args()

    if not 1 <= args.fps <= 120:
        sys.exit('Error: FPS must be between 1 and 120')
    if args.width < 20 or args.height < 10:
        sys.exit('Error: Width >= 20 and height >= 10 required')
    if not 10 <= args.fov <= 170:
        sys.exit('Error: FOV must be between 10 and 170 degrees')

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
