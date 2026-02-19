# ASCII 3D Model Renderer

A zero-dependency Python CLI that renders spinning 3D models and an infinite procedural forest world in the terminal using ASCII shading, per-pixel point-light illumination, true-colour edge lines, and perspective camera navigation.

## How This Code Was Generated

**This entire project was written by AI, guided by a human developer through iterative prompt-feedback cycles using [Kilo Code](https://kilocode.ai) in VS Code.**

The bulk of the development — planning, initial implementation, projection fixes, aspect ratio corrections, edge colouring, flicker reduction, multi-model support, and the rendering engine architecture — was done by a **locally-hosted [MiniMax-M2.5 (AWQ 4-bit)](https://huggingface.co/cyankiwi/MiniMax-M2.5-AWQ-4bit) model** running on a **2-node DGX Spark cluster** via [spark-vllm-docker](https://github.com/eugr/spark-vllm-docker) (with an updated recipe from [Spark Arena](https://spark-arena.com/leaderboard), which also provides an LLM leaderboard for models running on the NVIDIA DGX Spark along with supporting usage instructions), across two sessions (256 tool exchanges, 23 completion cycles). The human developer guided the flow at every step: identifying visual bugs, requesting features, and steering the model through dozens of refinement cycles to get the rendering right.

The project was then **extended significantly with [Claude Opus 4.6](https://www.anthropic.com/claude)** across three sessions (262 tool exchanges, 43 completion cycles), which handled: distortion analysis, quaternion-based rotation, auto-fit scaling, a new per-pixel lighting system, additional models (car, house scene), occlusion/culling fixes, documentation, free camera navigation with perspective projection, and a full procedural infinite forest world with terrain, mountains, and distance fog.

| Phase | Model | Sessions | Steps | Tool Exchanges | Description |
|-------|-------|----------|-------|----------------|-------------|
| Core development | Local MiniMax-M2.5 Cluster | 2 | 23 | 256 | Rendering engine, projection, shading, edge lines, multi-model |
| Analysis & polish | Opus 4.6 | 1 | 18 | 89 | Quaternion rotation, per-pixel lighting, z-buffer, car & house models |
| Camera & movement | Opus 4.6 | 1 | 4 | 29 | Free camera, perspective projection, key-state tracking, FOV config |
| Forest & terrain | Opus 4.6 | 1 | 21 | 144 | Infinite forest, terrain noise, mountains, distance fog, colour fading |
| **Total** | | **5** | **66** | **518** | |

📋 **[Full prompt history →](prompt_history.md)** — every user prompt and assistant completion across all 5 sessions, extracted from the raw task logs.

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
| Forest | [![asciicast](https://asciinema.org/a/FkN6ZmarYAWlxQ1N)](https://asciinema.org/a/FkN6ZmarYAWlxQ1N) |

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
- **Chunk streaming** — 12×12 world-unit chunks load/unload around the camera
- **Multi-tier pine trees** — 3-layer canopy with trunk (16 faces each)
- **Terrain** — two-octave smoothed value noise for rolling hills and valleys
- **Mountains** — rare, very large peaks via low-frequency noise with cubic power curve
- **Guaranteed landmark** — a 30-unit gaussian peak behind the spawn point for easy testing
- **Distance fog** — quadratic fade on both fill characters and edge colours
- **Height-based fog** — mountain terrain wireframe stays visible above the fog layer
- **Dynamic render distance** — see further from mountaintops (auto-expands chunk range)
- **Extended mountain loading** — mountain chunks load as terrain-only wireframe at 3× normal range

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
├── Forest primitives      make_pine_tree, make_rock, make_bush, make_ground_quad
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
| **Chunk streaming** | Load/unload 12×12 world-unit chunks around camera; 8 mountain chunks/frame budget |
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
├── run.py                                           # All code — models, renderer, forest, CLI (~1830 lines)
├── extract_prompts.py                               # Script to extract prompt history from task logs
├── prompt_history.md                                # Extracted prompt history (generated)
├── plans/
│   └── procedural_forest_plan.md                    # Architecture plan for the forest system
├── kilo_code_task_feb-19-2026_9-37-22-am.md         # Session 1 raw task log (MiniMax)
├── kilo_code_task_feb-19-2026_12-30-00-pm.md        # Session 2 raw task log (MiniMax)
├── opus_kilo_code_task_feb-19-2026_2-37-48-pm.md    # Session 3 raw task log (Opus)
├── opus_kilo_code_task_feb-19-2026_7-34-40-pm.md    # Session 4 raw task log (Opus)
├── opus_kilo_code_task_feb-19-2026_10-36-17-pm.md   # Session 5 raw task log (Opus)
├── README.md                                        # This file
└── PLAN.md                                          # Original project plan
```

## Exit

Press `Q` or `Ctrl+C` to stop the animation cleanly.

## License

MIT License
