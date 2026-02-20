# ASCII 3D Model Renderer

A zero-dependency Python CLI that renders spinning 3D models and an infinite procedural forest world in the terminal using ASCII shading, per-pixel point-light illumination, true-colour edge lines, and perspective camera navigation. Also includes a full **HTML/JavaScript/WebGL port** that runs in any browser.

## How This Code Was Generated

**This entire project was written by AI, guided by a human developer through iterative prompt-feedback cycles using [Kilo Code](https://kilocode.ai) in VS Code.**

The bulk of the development — planning, initial implementation, projection fixes, aspect ratio corrections, edge colouring, flicker reduction, multi-model support, and the rendering engine architecture — was done by a **locally-hosted [MiniMax-M2.5 (AWQ 4-bit)](https://huggingface.co/cyankiwi/MiniMax-M2.5-AWQ-4bit) model** running on a **2-node DGX Spark cluster** via [spark-vllm-docker](https://github.com/eugr/spark-vllm-docker) (with an updated recipe from [Spark Arena](https://spark-arena.com/leaderboard), which also provides an LLM leaderboard for models running on the NVIDIA DGX Spark along with supporting usage instructions), across two sessions (256 tool exchanges, 23 completion cycles). The human developer guided the flow at every step: identifying visual bugs, requesting features, and steering the model through dozens of refinement cycles to get the rendering right.

The project was then **extended significantly with [Claude Opus 4.6](https://www.anthropic.com/claude)** across three sessions (262 tool exchanges, 43 completion cycles), which handled: distortion analysis, quaternion-based rotation, auto-fit scaling, a new per-pixel lighting system, additional models (car, house scene), occlusion/culling fixes, documentation, free camera navigation with perspective projection, and a full procedural infinite forest world with terrain, mountains, and distance fog.

The entire Python terminal renderer was then **ported to HTML/JavaScript/WebGL** in a single Opus 4.6 session (42 tool exchanges, 2 completion cycles). This session analyzed all 22 subsystems in `run.py`, created a detailed architecture plan, then implemented 9 ES modules plus HTML/CSS — translating the CPU-based ASCII rasterizer into GPU-accelerated WebGL with GLSL shaders for lighting, fog, and wireframe rendering.

A **sky/horizon backdrop and rendering optimisation** session (105 tool exchanges, 18 completion cycles) added a gradient sky shader to the WebGL port, implemented three-tier chunk loading (full detail → terrain-only → mountain-only) to eliminate visual gaps between nearby and distant terrain, and applied five performance optimisations to the Python renderer: scanline rasteriser, inlined camera transforms, single-pass vertex projection, incremental z-interpolation in line drawing, and a fog-faded edge string cache.

Most recently, a **special tree and yellow path** session (80 tool exchanges, 7 completion cycles) added a unique "golden oak" tree to the forest — visually distinct from regular pine trees with a thicker trunk and rounded canopy. The tree spawns at a random location 5-8 units from the player's spawn position (approximately 10 seconds walk away). A yellow diamond-shaped path is drawn from the player's starting location to the special tree, implemented in both the Python terminal renderer and the WebGL port.

| Phase | Model | Sessions | Steps | Tool Exchanges | Description |
|-------|-------|----------|-------|----------------|-------------|
| Core development | Local MiniMax-M2.5 Cluster | 2 | 23 | 256 | Rendering engine, projection, shading, edge lines, multi-model |
| Analysis & polish | Opus 4.6 | 1 | 18 | 89 | Quaternion rotation, per-pixel lighting, z-buffer, car & house models |
| Camera & movement | Opus 4.6 | 1 | 4 | 29 | Free camera, perspective projection, key-state tracking, FOV config |
| Forest & terrain | Opus 4.6 | 1 | 21 | 144 | Infinite forest, terrain noise, mountains, distance fog, colour fading |
| WebGL port | Opus 4.6 | 1 | 2 | 42 | Full HTML/JS/WebGL port of the Python terminal renderer |
| Sky & optimisations | Opus 4.6 | 1 | 18 | 105 | WebGL sky shader, three-tier chunk loading, Python renderer optimisations |
| Special tree & path | Opus 4.6 | 1 | 7 | 80 | Golden oak tree with unique canopy, yellow path markers from spawn |
| **Total** | | **8** | **93** | **745** | |

📋 **[Full prompt history →](prompt_history.md)** — every user prompt and assistant completion across all 7 sessions, extracted from the raw task logs.

## Requirements

- Python 3.6+
- Unix-like OS (Linux, macOS) — required for non-blocking keyboard input via `termios`
- Terminal with ANSI 24-bit true-colour support (most modern terminals)

## Examples

| Model | Recording |
|-------|-----------|
| Cube | [![asciicast](https://asciinema.org/a/oKZXRAfmjrFImdfE.svg)](https://asciinema.org/a/oKZXRAfmjrFImdfE) |
| Car | [![asciicast](https://asciinema.org/a/YYQU4E8z3ssmdCUO.svg)](https://asciinema.org/a/YYQU4E8z3ssmdCUO) |
| House | [![asciicast](https://asciinema.org/a/pxwMuETRzf91jQm5.svg)](https://asciinema.org/a/pxwMuETRzf91jQm5) |
| Forest | [![asciicast](https://asciinema.org/a/FkN6ZmarYAWlxQ1N.svg)](https://asciinema.org/a/FkN6ZmarYAWlxQ1N) |
| WebGL Port | [![WebGL Port](https://img.youtube.com/vi/6YKX-42oFKo/maxresdefault.jpg)](https://www.youtube.com/watch?v=6YKX-42oFKo) |

## Quick Start

```bash
python3 run.py                     # spinning cube (default)
python3 run.py --model car         # low-poly sedan
python3 run.py --model house       # house scene with garden and trees
python3 run.py --forest            # infinite procedural forest world
```

Or make it executable:

```bash
chmod +x run.py
./run.py --model house
./run.py --forest --seed 123       # forest with custom seed
```

## WebGL Port

A full HTML/JavaScript/WebGL port of the Python terminal renderer lives in `webgl-port/`. It requires no build step — just serve the directory with any HTTP server:

```bash
cd webgl-port && python3 -m http.server 8080
# Then open http://localhost:8080
```

The WebGL port supports the same three modes (spin, move, forest) and all three models (cube, car, house) via clickable UI buttons. URL parameters mirror the CLI options:

```
http://localhost:8080/?model=car          # start with car model
http://localhost:8080/?forest             # start in forest mode
http://localhost:8080/?forest&seed=123    # forest with custom seed
http://localhost:8080/?move&fov=110       # move mode with wider FOV
```

### Key Differences from Python Original

| Feature | Python (terminal) | WebGL Port |
|---------|-------------------|------------|
| Sky / horizon | — (removed for perf) | GLSL gradient shader + fullscreen quad |
| Rasterization | CPU scanline + z-buffer | GPU hardware |
| Clipping | Sutherland-Hodgman CPU | GPU native |
| Edges | Bresenham line drawing | `GL_LINES` with depth bias |
| Shading | Per-pixel ASCII brightness chars | GLSL point-light + fog |
| Output | ASCII characters in terminal | Smooth WebGL canvas rendering |
| Integer math | Arbitrary precision | `Math.imul()` for 32-bit fidelity |

## Modes

### Spin Mode (default)

Models auto-rotate with orthographic projection. Press **Tab** to switch to movement mode.

### Movement Mode

Free camera navigation with perspective projection. Start directly with `--move`:

```bash
python3 run.py --model house --move
```

**Controls:**

| Key | Action |
|-----|--------|
| W / Up | Move forward |
| S / Down | Move backward |
| A | Strafe left |
| D | Strafe right |
| Left / Right | Turn left / right |
| R / Space | Move up |
| F | Move down |
| E / C | Pitch up / down |
| Tab | Switch to spin mode |
| Q / Ctrl-C | Quit |

### Forest Mode

An infinite procedurally generated forest with trees, rocks, bushes, rolling terrain, and mountains. Uses chunk-based streaming — new terrain loads as you walk.

```bash
python3 run.py --forest                        # default seed 42
python3 run.py --forest --seed 123             # custom seed
python3 run.py --forest --render-dist 3        # larger view distance
python3 run.py --forest --fov 110              # wider field of view
```

**Features:**
- **Procedural generation** — deterministic seeded RNG; same seed = same world
- **Three-tier chunk streaming** — 12×12 world-unit chunks: full detail nearby, terrain-only at mid-range, mountain-only at far range
- **Multi-tier pine trees** — 3-layer canopy with trunk (16 faces each)
- **Special golden oak tree** — unique tree with thicker trunk and rounded canopy, spawned at random location 5-8 units from player spawn
- **Yellow path markers** — diamond-shaped golden markers drawn from spawn location to the special tree
- **Terrain** — two-octave smoothed value noise for rolling hills and valleys
- **Mountains** — rare, very large peaks via low-frequency noise with cubic power curve
- **Guaranteed landmark** — a 30-unit gaussian peak behind the spawn point for easy testing
- **Distance fog** — quadratic fade on both fill characters and edge colours
- **Height-based fog** — mountain terrain wireframe stays visible above the fog layer
- **Dynamic render distance** — see further from mountaintops (auto-expands chunk range)
- **Extended mountain loading** — mountain chunks load as terrain-only wireframe at 3× normal range
- **Sky backdrop** (WebGL only) — gradient sky shader with horizon band; fog colour matched to horizon for seamless blending

## Models

| Model | Vertices | Faces | Description |
|-------|----------|-------|-------------|
| `cube` | 8 | 6 quads | Unit cube centred at origin |
| `car` | 16 | 12 quads | Low-poly sedan (body + cabin + roof) |
| `house` | 28 | 20 (quads + triangles) | House with pitched roof, garden ground, two trees |

Select with `--model` / `-m`:

```bash
python3 run.py -m cube
python3 run.py -m car
python3 run.py -m house
```

## Command-Line Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--model` | `-m` | `cube` | Model to render (`cube`, `car`, `house`) |
| `--width` | `-w` | Terminal width | Console width in characters |
| `--height` | `-H` | Terminal height − 1 | Console height in lines |
| `--size` | `-s` | `1.5` | Model size multiplier |
| `--fps` | `-f` | `30` | Frames per second (1–120) |
| `--speed-y` | | `0.03` | Y-axis rotation speed (rad/frame) |
| `--speed-x` | | `0.01` | X-axis rotation speed (rad/frame) |
| `--speed-z` | | `0.02` | Z-axis rotation speed (rad/frame) |
| `--rotate-z` | | off | Enable Z-axis rotation |
| `--move` | | off | Start in movement mode (free camera) |
| `--fov` | | `90` | Horizontal field of view in degrees (10–170) |
| `--forest` | | off | Start in infinite procedural forest mode |
| `--seed` | | `42` | World seed for forest generation |
| `--render-dist` | | `2` | Chunk render distance for forest |
| `--frame` | `-fr` | — | Render a single frame number and exit |

## Usage Examples

```bash
# Default spinning cube
python3 run.py

# Larger house, all-axis rotation
python3 run.py --model house --size 2 --rotate-z

# Static frame for debugging
python3 run.py --model car --frame 80 --width 100 --height 30

# Fast smooth animation
python3 run.py --fps 60 --speed-y 0.05

# Small viewport
python3 run.py --width 60 --height 20

# Navigate around the house
python3 run.py --model house --move --fov 90

# Explore a procedural forest
python3 run.py --forest

# Forest with custom seed and wider view
python3 run.py --forest --seed 999 --render-dist 3 --fov 110
```

## Rendering Engine

### Architecture

```
run.py
├── Vec3                   3D vector (dot, normalize)
├── Quaternion             Unit quaternion rotation (axis-angle, Hamilton product)
├── Camera                 First-person camera (position, yaw/pitch, view transform)
├── Model                  Base class (vertices, faces, rotate, bounding radius)
│   ├── Cube               8 verts, 6 quad faces
│   ├── Car                16 verts, 12 quad faces
│   └── HouseScene         28 verts, 20 mixed tri/quad faces
├── Forest primitives      make_pine_tree, make_oak_tree, make_rock, make_bush, make_ground_quad
├── Terrain system         terrain_height (3-layer noise), make_terrain_grid
├── ForestChunk            Seeded procedural chunk with objects + terrain grid
├── ForestWorld            Chunk-based streaming manager (duck-typed as Model)
├── KeyboardInput          Non-blocking terminal input (termios/select)
├── Renderer               ASCII rasteriser with z-buffer (ortho + perspective)
└── SpinningModel          CLI application / animation loop
```

### Features

| Feature | Implementation |
|---------|---------------|
| **Rotation** | Quaternion composition — no gimbal lock, no floating-point drift (periodic re-normalisation) |
| **Orthographic projection** | Auto-fit scaling to fill the terminal viewport (spin mode) |
| **Perspective projection** | Camera-space transform with configurable FOV and focal length (move mode) |
| **Near-plane clipping** | Sutherland-Hodgman polygon clipping against `cam_z = near` |
| **Back-face culling** | `normal.z > 0` test in ortho mode; disabled in perspective (z-buffer handles it) |
| **Occlusion** | Per-pixel z-buffer depth test (not painter's algorithm) |
| **Shading** | Per-pixel Lambertian point-light with inverse-square attenuation and ambient term |
| **Shading gradient** | 8-level ASCII ramp: `.:-=+*%@` |
| **Edge lines** | Bresenham's algorithm with z-buffered depth test; `#9fef00` ANSI 24-bit true-colour |
| **Edge fog** | Edge RGB colours fade toward black with distance (quadratic, matches fill fog) |
| **Face types** | Supports 3-vertex (triangle) and 4-vertex (quad) faces, plus wireframe-only |
| **Auto-fit** | Model's bounding sphere is scaled to fit the viewport with margin |
| **Distance fog** | Per-pixel quadratic fade; fully fogged pixels skipped for performance |
| **Height-based fog** | Mountain terrain wireframe gets reduced fog so peaks remain visible at range |
| **Procedural terrain** | Two-octave value noise (rolling hills) + low-frequency mountain layer |
| **Special tree** | Golden oak tree with thick trunk and rounded canopy, spawned 5-8 units from player |
| **Yellow path** | Diamond-shaped markers with bright yellow edges from spawn to special tree |
| **Scanline rasteriser** | Edge-intersection traversal replacing bounding-box + point-in-polygon (Python) |
| **Chunk streaming** | Three-tier loading: full detail, terrain-only, mountain-only; 8 chunks/frame budget |
| **Sky gradient** | Fullscreen quad GLSL shader with zenith→horizon→ground gradient (WebGL only) |
| **Camera tracking** | Camera Y follows terrain height; dynamic render distance from elevation |

### How It Works

1. **Model definition** — Each model subclass provides vertex positions and face index tuples (CCW winding from outside).
2. **Quaternion rotation** — Per-frame axis-angle quaternions are composed into a cumulative orientation; all vertices are rebuilt from originals each frame to avoid drift.
3. **Orthographic projection** — World coordinates are scaled and offset to screen space; character aspect ratio (2:1) is compensated.
4. **Perspective projection** — Camera view transform converts world→camera space; `screen_x = focal × cam_x / cam_z + cx`.
5. **Near-plane clipping** — Faces straddling `cam_z = near` are clipped via Sutherland-Hodgman rather than discarded.
6. **Z-buffered face fill** — For each visible face, every pixel inside the polygon is tested. The face plane equation reconstructs the depth at each pixel; only the closest pixel survives.
7. **Per-pixel lighting** — The 3D position of each pixel is used to compute a light-direction vector, diffuse `dot(N, L)`, and inverse-square attenuation, producing smooth shading gradients across each face.
8. **Z-buffered edge draw** — Edge lines interpolate z along the Bresenham path with a small bias to sit in front of their face plane but behind closer geometry. Edge colours fade with distance.
9. **Chunk streaming** — `ForestWorld.update()` loads/unloads chunks based on camera position; mountain chunks load at extended range as terrain-only wireframe with coarser grid resolution.
10. **Terrain generation** — `terrain_height()` evaluates 3 noise layers (2 rolling-hill octaves + mountain) plus a guaranteed gaussian landmark peak near spawn.

## File Structure

```
m25test/
├── run.py                                           # Python terminal renderer (~1965 lines)
├── webgl-port/                                      # HTML/JS/WebGL port (Sessions 6–7)
│   ├── index.html                                   # Canvas + HUD overlay
│   ├── css/style.css                                # Dark theme, green accent
│   └── js/
│       ├── math.js                                  # Vec3, Quaternion, mat4 utilities
│       ├── camera.js                                # First-person camera (yaw/pitch, view matrix)
│       ├── input.js                                 # Keyboard input manager
│       ├── models.js                                # Cube, Car, HouseScene geometry builders
│       ├── terrain.js                               # Procedural terrain height + grid generation
│       ├── forest.js                                # Forest primitives + chunk streaming
│       ├── renderer.js                              # WebGL renderer (fill + wireframe shaders)
│       └── main.js                                  # Entry point, modes, animation loop
├── extract_prompts.py                               # Script to extract prompt history from task logs
├── prompt_history.md                                # Extracted prompt history (generated)
├── README.md                                        # This file
```

## Exit

Press `Q` or `Ctrl+C` to stop the animation cleanly.

## License

MIT License
