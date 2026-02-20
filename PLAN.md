# CLI 3D Spinning Cube - Project Plan

## 1. Project Overview

Create a CLI script that renders a spinning 3D cube using ASCII "shading" to represent depth and surface normals. The cube will rotate continuously, with the rendering updating in real-time in the terminal.

## 2. Environment

- **OS**: Ubuntu 24.04.3 LTS (Debian-based)
- **Python**: 3.12.3
- **Terminal**: ANSI-compatible terminal (most modern terminals support this)

## 3. Technical Approach

### 3.1 Core Components

1. **3D Cube Model**
   - Define 8 vertices of a unit cube centered at origin
   - Define 6 faces (each with 4 vertices and a normal vector)
   - Use vertices: (±1, ±1, ±1) normalized to unit length

2. **3D Math Operations**
   - Rotation matrices for X, Y, Z axis rotation
   - Matrix multiplication for combining rotations
   - Vertex transformation (apply rotation matrix)
   - Normal transformation (for lighting calculation)

3. **Projection System**
   - Perspective projection: 3D → 2D screen coordinates
   - Map 3D points to terminal character grid
   - Handle depth (Z) for proper occlusion

4. **ASCII "Shader"**
   - Calculate face visibility using dot product (back-face culling)
   - Calculate lighting intensity using dot product of face normal and light direction
   - Map intensity to ASCII character gradient: ` .:-=+*#%@`
   - Depth sorting for proper rendering order (painter's algorithm)

5. **Animation Loop**
   - Continuous rotation around Y-axis (and optionally X-axis)
   - Frame rate control (30-60 FPS target)
   - Clear screen and reposition cursor between frames

### 3.2 Implementation Options

**Option A: Pure Python (No Dependencies)**
- Pros: Zero external dependencies, runs everywhere
- Cons: Slower performance, manual math

**Option B: NumPy**
- Pros: Faster matrix operations, cleaner code
- Cons: Requires `pip install numpy`

**Recommended**: Start with Option A (Pure Python) for simplicity and portability

## 4. File Structure

```
m25test/
├── PLAN.md                 # This plan
├── cube.py                 # Main CLI script
└── README.md               # Usage instructions
```

## 5. Implementation Steps

### Step 1: Core Math Module
- [ ] Create `Cube3D` class with vertices and faces
- [ ] Implement rotation matrices (X, Y, Z)
- [ ] Implement vertex transformation
- [ ] Implement normal transformation

### Step 2: Projection System
- [ ] Implement perspective projection (3D → 2D)
- [ ] Calculate screen coordinates
- [ ] Handle viewport/terminal size

### Step 3: Rendering Engine
- [ ] Implement back-face culling
- [ ] Implement depth sorting (painter's algorithm)
- [ ] Implement ASCII shading based on lighting
- [ ] Create character gradient for shading

### Step 4: Animation & CLI
- [ ] Implement animation loop
- [ ] Add frame rate control
- [ ] Add terminal screen clearing
- [ ] Add keyboard interrupt handling

### Step 5: Enhancements (Optional)
- [ ] Add command-line arguments (speed, size, axis)
- [ ] Add color support (ANSI colors)
- [ ] Add wireframe mode option

## 6. CLI Interface

```bash
# Run with defaults
python3 cube.py

# With options
python3 cube.py --speed 30 --size 50
python3 cube.py --help
```

## 7. Acceptance Criteria

- [ ] Cube renders as a 3D object in terminal
- [ ] Cube rotates smoothly (no flickering)
- [ ] Faces are shaded based on orientation (lighting effect)
- [ ] Back faces are not visible (culling works)
- [ ] Runs without external dependencies
- [ ] Clean exit on Ctrl+C

## 8. Key Algorithms

### Rotation Matrix (Y-axis example)
```
x' = x*cos(θ) - z*sin(θ)
y' = y
z' = x*sin(θ) + z*cos(θ)
```

### Back-face Culling
```
visible = dot(face_normal, camera_vector) > 0
```

### Lighting Intensity
```
intensity = dot(face_normal, light_direction)
```

### Perspective Projection
```
screen_x = x / (z + distance) * scale + center_x
screen_y = y / (z + distance) * scale + center_y
```

## 9. Estimated Development Time

- Core implementation: 30-45 minutes
- Testing & refinement: 15-20 minutes
- Total: ~1 hour

## 10. References

- ASCII 3D engines: https://asciimoo.github.io/
- Rotation matrices: Standard 3D graphics textbooks
- ANSI escape codes: https://en.wikipedia.org/wiki/ANSI_escape_code