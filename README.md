# ADAS Vision 3D

A single-camera driver-assistance prototype. It detects vehicles and traffic signs in a dashcam video, estimates their distance and relative speed, decides on braking, speed and lane changes, and shows the scene live in 3D in Godot.

Built by team **MaybeWorks** at **ProveIT Hackathon 2026** for the **Magna** computer-vision challenge.

---

## What it does

| Stage | How |
|---|---|
| **Vehicle detection & tracking** | [RT-DETR](https://docs.ultralytics.com/models/rtdetr/) (`rtdetr-l.pt`) via Ultralytics, with persistent track IDs; keeps `car`, `truck`, `bus` |
| **Traffic-sign detection** | Custom **YOLOv8** model (`traffic_signs_v8.pt`) |
| **Lane & drivable area** | **YOLOP** (drivable-area segmentation), combined with Canny + Hough lane lines smoothed over time, to get the ego lane |
| **Distance estimation** | Pinhole-camera model from one camera: `distance = real_width × focal_length / box_width_px` (car ≈ 1.8 m, truck/bus ≈ 2.5 m, sign ≈ 0.6 m) |
| **Relative speed** | Change in each tracked object's distance between updates, in km/h |
| **Risk & decision logic** | Labels each object (`foarte_aproape` / `aproape` / `departe` / `risc_lateral` / `ignorat_extern`) and outputs risk level, braking, speed decision and lane decision |
| **Visualization** | OpenCV overlay + HUD, a 2D radar view, and a live **3D scene in Godot 4** |

### Decision rules (summary)

- Vehicle in the ego lane **< 8 m** → strong braking, high risk
- Vehicle in the ego lane **< 20 m** → light braking, medium risk
- Vehicle in an adjacent lane, close → lateral risk (medium)
- **Stop / yield / no-entry** sign → strong braking
- **Speed-limit** sign → light braking, slow down
- Lane decision (`mentinere` / `schimbare_stanga` / `schimbare_dreapta`) comes from where the car sits between the detected lane lines

The heavy models run every 0.5 s. Drawing runs on every frame at the video's own frame rate.

### Architecture

```
video ──► app.py ──────────────────────────────► OpenCV window (overlay + HUD)
          │  RT-DETR + YOLOv8 + YOLOP + Hough
          │  distance / speed / decision logic
          │
          ├──► date_pentru_opengl.json  (written atomically every 0.5 s)
          │         │
          │         ├──► randare.py         2D radar (OpenCV)
          │         ├──► randare_3D.py      3D view (Ursina, Python)
          │         └──► randarea-3d/       3D view (Godot 4.6)
          │
          └──► istoric_decizii.log  (decision history)
```

---

## Team & contributions

- **Rareș Hamburda** ([@Hamburda](https://github.com/Hamburda)): vehicle and traffic-sign detection, distance and relative-speed estimation, risk / braking / lane-change decision logic, and the live 3D visualization in Godot.
- **Mihai Stratulescu** and **Beatrice**: lane detection (YOLOP).

---

## Getting started

### 1. Install

Python 3.9+ is recommended. A CUDA GPU is used automatically if available, otherwise the app runs on the CPU.

```bash
git clone https://github.com/Hamburda/adas-vision-3d.git
cd adas-vision-3d
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Get the models and a video

The model weights and videos are not in the repository because they are too large. Put these files in the repository root:

| File | Source |
|---|---|
| `rtdetr-l.pt` | Official Ultralytics weights. **Downloaded automatically** on first run. |
| `traffic_signs_v8.pt` | Custom YOLOv8 traffic-sign model: **[download link]** |
| YOLOP | Downloaded automatically by `torch.hub` from [hustvl/YOLOP](https://github.com/hustvl/YOLOP) on first run (needs internet). |
| `video1.mp4` | Dashcam test video: **[download link]**. Any front-facing dashcam video works. |

### 3. Run

```bash
python app.py
```

`app.py` loads the models, opens the video, and starts `randare.py` (2D radar) and `randare_3D.py` (Ursina 3D view) automatically. Press **`q`** in the video window to quit.

Settings are at the top of `app.py`:

- `VIDEO_INPUT`: input video (default `video1.mp4`)
- `MINUTUL_DE_START`: minute of the video to start from (default `2`)
- `FOCAL_L`: focal length in pixels used for distance estimation (default `250`)

### 4. 3D visualization in Godot

1. Install [Godot 4.6](https://godotengine.org/download/).
2. With `app.py` running, open the `randarea-3d/` folder as a project in Godot.
3. Press **Play** (F5).

The scene reads `date_pentru_opengl.json` from the repository root every 0.1 s and moves each tracked vehicle smoothly to its new position. Vehicles are colored by risk: red for danger, orange for trucks/buses, green for other cars, grey for ignored objects.

**Camera controls:** `W/A/S/D` move · `Q/E` down/up · mouse wheel zoom · right-click + drag rotate · `R` reset.

### Lane-detection demo (standalone)

```bash
python main.py
```

Runs YOLOP on `video1.mp4` and highlights the lane lines in green.

---

## Project structure

```
app.py                    main pipeline: detection, tracking, distance, speed, decisions, HUD
main.py                   standalone YOLOP lane-detection demo
randare.py                2D radar view (reads the JSON)
randare_3D.py             3D view in Python / Ursina (reads the JSON)
randarea-3d/              Godot 4.6 project for the live 3D view
  ├── main.gd             builds the road scene and HUD, syncs vehicles from the JSON
  ├── camera.gd           free-fly / orbit camera
  └── main.tscn
date_pentru_opengl.json   example output frame (overwritten at runtime)
50_test.jpg               test image
requirements.txt
```

### Output format (`date_pentru_opengl.json`)

```json
{
  "timestamp": "2026-04-05T05:59:12.801187",
  "perceptie": [
    { "id": 14, "tip": "car", "coords": [256, 257, 293, 291],
      "metri": 12.2, "distanta_estimata": "aproape", "viteza_relativa_kmh": -5.5 }
  ],
  "risc": "mediu",
  "brake": "franare_usoara",
  "speed_decision": "scadere",
  "lane_decision": "mentinere",
  "semn_activ": "Niciunul"
}
```

---

## Notes and limitations

- Distance comes from one camera and assumed vehicle widths, so it is an estimate. It is most accurate for vehicles seen from behind.
- `FOCAL_L` and the lateral offsets in the viewers were tuned by hand for the hackathon videos. A different camera will need new values.
- The project was developed on Windows. The Godot project uses Direct3D 12 there and Godot's default renderer on other systems.
