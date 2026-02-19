# ASCII 3D Model Renderer

A zero-dependency Python CLI that renders spinning 3D models in the terminal using ASCII shading, per-pixel point-light illumination, and true-colour edge lines.

## How This Code Was Generated

**This entire project was written by AI, guided by a human developer through iterative prompt-feedback cycles using [Kilo Code](https://kilocode.ai) in VS Code.**

The bulk of the development — planning, initial implementation, projection fixes, aspect ratio corrections, edge colouring, flicker reduction, multi-model support, and the rendering engine architecture — was done by a **locally-hosted [MiniMax-M2.5 (AWQ 4-bit)](https://huggingface.co/cyankiwi/MiniMax-M2.5-AWQ-4bit) model** running on a **2-node DGX Spark cluster** via [spark-vllm-docker](https://github.com/eugr/spark-vllm-docker) (with an updated recipe from [Spark Arena](https://spark-arena.com/leaderboard), which also provides an LLM leaderboard for models running on the NVIDIA DGX Spark along with supporting usage instructions), across two sessions (433 tool exchanges, 23 completion cycles). The human developer guided the flow at every step: identifying visual bugs, requesting features, and steering the model through dozens of refinement cycles to get the rendering right.

The project was then **finished off with [Claude Opus 4.6](https://www.anthropic.com/claude)**, which handled the final polish: distortion analysis, quaternion-based rotation, auto-fit scaling, a new per-pixel lighting system, additional models (car, house scene), occlusion/culling fixes, and documentation.

| Phase | Model | Sessions | Steps | Tool Exchanges |
|-------|-------|----------|-------|----------------|
| Core development | Local MiniMax-M2.5 Cluster | 2 | 23 | 433 |
| Analysis & polish | Opus 2.6 | 1 | 18 | 89 |

📋 **[Full prompt history →](prompt_history.md)** — every user prompt and assistant completion, extracted from the raw task logs.

## Requirements

- Python 3.6+
- Terminal with ANSI 24-bit true-colour support (most modern terminals)

## Examples

| Model | Recording |
|-------|-----------|
| Cube | [![asciicast](https://asciinema.org/a/oKZXRAfmjrFImdfE.svg)](https://asciinema.org/a/oKZXRAfmjrFImdfE) |
| Car | [![asciicast](https://asciinema.org/a/YYQU4E8z3ssmdCUO.svg)](https://asciinema.org/a/YYQU4E8z3ssmdCUO) |
| House | [![asciicast](https://asciinema.org/a/pxwMuETRzf91jQm5.svg)](https://asciinema.org/a/pxwMuETRzf91jQm5) |

## Quick Start

```bash
python3 run.py                     # spinning cube (default)
python3 run.py --model car         # low-poly sedan
python3 run.py --model house       # house scene with garden and trees
```

Or make it executable:

```bash
chmod +x run.py
./run.py --model house
```

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
```

## Rendering Engine

### Architecture

```
run.py
├── Vec3              3D vector (dot, normalize)
├── Quaternion        Unit quaternion rotation (axis-angle, Hamilton product)
├── Model             Base class (vertices, faces, rotate, bounding radius)
│   ├── Cube          8 verts, 6 quad faces
│   ├── Car           16 verts, 12 quad faces
│   └── HouseScene    28 verts, 20 mixed tri/quad faces
├── Renderer          ASCII rasteriser with z-buffer
└── SpinningModel     CLI application / animation loop
```

### Features

| Feature | Implementation |
|---------|---------------|
| **Rotation** | Quaternion composition — no gimbal lock, no floating-point drift (periodic re-normalisation) |
| **Projection** | Orthographic with auto-fit scaling to fill the terminal viewport |
| **Back-face culling** | `normal.z > 0` test on transformed normals |
| **Occlusion** | Per-pixel z-buffer depth test (not painter's algorithm) |
| **Shading** | Per-pixel Lambertian point-light with inverse-square attenuation and ambient term |
| **Shading gradient** | 8-level ASCII ramp: `.:-=+*%@` |
| **Edge lines** | Bresenham's algorithm with z-buffered depth test; `#9fef00` ANSI 24-bit true-colour |
| **Face types** | Supports 3-vertex (triangle) and 4-vertex (quad) faces |
| **Auto-fit** | Model's bounding sphere is scaled to fit the viewport with margin |

### How It Works

1. **Model definition** — Each model subclass provides vertex positions and face index tuples (CCW winding from outside).
2. **Quaternion rotation** — Per-frame axis-angle quaternions are composed into a cumulative orientation; all vertices are rebuilt from originals each frame to avoid drift.
3. **Orthographic projection** — World coordinates are scaled and offset to screen space; character aspect ratio (2:1) is compensated.
4. **Back-face culling** — Only faces whose transformed normal has `z > 0` (facing the camera) are drawn.
5. **Z-buffered face fill** — For each visible face, every pixel inside the polygon is tested. The face plane equation reconstructs the world-z at each pixel; only the closest pixel survives.
6. **Per-pixel lighting** — The 3D position of each pixel is used to compute a light-direction vector, diffuse `dot(N, L)`, and inverse-square attenuation, producing smooth shading gradients across each face.
7. **Z-buffered edge draw** — Edge lines interpolate z along the Bresenham path with a small bias to sit in front of their face plane but behind closer geometry.

## File Structure

```
m25test/
├── run.py               # All code — models, renderer, CLI
├── extract_prompts.py   # Script to extract prompt history from task logs
├── prompt_history.md    # Extracted prompt history (generated)
├── README.md            # This file
└── PLAN.md              # Original project plan
```

## Exit

Press `Ctrl+C` to stop the animation cleanly.

## License

MIT License
