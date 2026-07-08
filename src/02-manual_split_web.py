"""
    python 02-manual_split_web.py --folder ./scans/ --out ./split/

Потім відкрий браузер: http://localhost:5000
"""

import cv2
import numpy as np
import base64
import argparse
import json
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, send_file

app = Flask(__name__)

# Глобальний стан
STATE = {
    "images": [],
    "current": 0,
    "out_dir": "./split",
    "done": [],
    "skipped": [],
}

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Split Tool</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: monospace; background: #1a1a1a; color: #eee; }

  #header {
    position: fixed; top: 0; left: 0; right: 0;
    background: #111; padding: 10px 20px;
    display: flex; align-items: center; gap: 16px;
    z-index: 100; border-bottom: 1px solid #333;
  }
  #progress { font-size: 14px; color: #aaa; }
  #filename { font-size: 13px; color: #7af; flex: 1; }
  #spine-info { font-size: 13px; color: #fa0; min-width: 120px; }

  button {
    padding: 8px 18px; border: none; border-radius: 4px;
    cursor: pointer; font-size: 14px; font-family: monospace;
  }
  #btn-save   { background: #2a7; color: #fff; }
  #btn-skip   { background: #555; color: #eee; }
  #btn-save:hover { background: #3b8; }
  #btn-skip:hover { background: #666; }

  #canvas-wrap {
    margin-top: 52px;
    position: relative; display: inline-block; cursor: crosshair;
  }
  #canvas { display: block; }

  #done-msg {
    display: none; text-align: center;
    padding: 80px 20px; font-size: 22px; color: #2a7;
  }
</style>
</head>
<body>

<div id="header">
  <span id="progress">-/-</span>
  <span id="filename">-</span>
  <span id="spine-info">x = ?</span>
  <button id="btn-save" onclick="save()">✓ Зберегти (Enter)</button>
  <button id="btn-skip" onclick="skip()">→ Пропустити (S)</button>
</div>

<div id="canvas-wrap">
  <canvas id="canvas"></canvas>
</div>

<div id="done-msg">✓ Всі зображення оброблено!</div>

<script>
const canvas = document.getElementById('canvas');
const ctx    = canvas.getContext('2d');
let img      = new Image();
let spineX   = 0;      // у пікселях оригінального зображення
let scaleX   = 1;
let state    = {};

function loadCurrent() {
  fetch('/current').then(r => r.json()).then(data => {
    state = data;
    if (data.done) {
      document.getElementById('canvas-wrap').style.display = 'none';
      document.getElementById('done-msg').style.display = 'block';
      document.getElementById('header').style.display = 'none';
      return;
    }

    document.getElementById('progress').textContent =
      `${data.index + 1} / ${data.total}`;
    document.getElementById('filename').textContent = data.filename;

    img.onload = () => {
      // Масштабуємо до ширини вікна
      const maxW = window.innerWidth;
      const maxH = window.innerHeight - 60;
      const scale = Math.min(1, maxW / img.naturalWidth, maxH / img.naturalHeight);
      canvas.width  = Math.round(img.naturalWidth  * scale);
      canvas.height = Math.round(img.naturalHeight * scale);
      scaleX = scale;

      // Початкова пропозиція — авто корінець від сервера
      spineX = data.auto_spine;
      drawFrame();
    };
    img.src = '/image?t=' + Date.now();
  });
}

function drawFrame() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

  const sx = Math.round(spineX * scaleX);

  // Тінь ліворуч і праворуч від лінії
  ctx.fillStyle = 'rgba(0,0,0,0.25)';
  ctx.fillRect(sx - 1, 0, 2, canvas.height);

  // Лінія розрізу
  ctx.strokeStyle = '#ff3333';
  ctx.lineWidth   = 2;
  ctx.setLineDash([8, 4]);
  ctx.beginPath();
  ctx.moveTo(sx, 0);
  ctx.lineTo(sx, canvas.height);
  ctx.stroke();
  ctx.setLineDash([]);

  // Мітка
  ctx.fillStyle = '#ff3333';
  ctx.fillRect(sx - 30, 10, 60, 22);
  ctx.fillStyle = '#fff';
  ctx.font = 'bold 13px monospace';
  ctx.textAlign = 'center';
  ctx.fillText('x=' + spineX, sx, 25);

  document.getElementById('spine-info').textContent = 'x = ' + spineX;
}

canvas.addEventListener('mousemove', e => {
  const rect = canvas.getBoundingClientRect();
  const cx   = e.clientX - rect.left;
  spineX     = Math.round(cx / scaleX);
  drawFrame();
});

canvas.addEventListener('click', e => {
  // фіксуємо після кліку — mousemove вже встановив spineX
  drawFrame();
});

function save() {
  fetch('/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ spine_x: spineX, filename: state.filename })
  }).then(r => r.json()).then(d => {
    if (d.ok) loadCurrent();
  });
}

function skip() {
  fetch('/skip', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ filename: state.filename })
  }).then(r => r.json()).then(d => {
    if (d.ok) loadCurrent();
  });
}

document.addEventListener('keydown', e => {
  if (e.key === 'Enter') save();
  if (e.key === 's' || e.key === 'S') skip();
  // Стрілки для тонкого підстроювання
  if (e.key === 'ArrowLeft')  { spineX -= 1; drawFrame(); }
  if (e.key === 'ArrowRight') { spineX += 1; drawFrame(); }
});

loadCurrent();
</script>
</body>
</html>
"""


def find_auto_spine(img_path: str) -> int:
    """Автоматична пропозиція корінця — можна підправити мишею."""
    img = cv2.imread(img_path)
    if img is None:
        return 0
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    col = np.mean(gray, axis=0)
    smoothed = np.convolve(col, np.ones(15) / 15, mode="same")
    gradient = np.gradient(smoothed)
    s = int(w * 0.46)
    e = int(w * 0.62)
    spine_x = int(np.argmin(gradient[s:e])) + s + 10  # +10px корекція
    return spine_x


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/current")
def current():
    images = STATE["images"]
    idx = STATE["current"]
    if idx >= len(images):
        return jsonify({"done": True})
    path = images[idx]
    img = cv2.imread(str(path))
    w = img.shape[1] if img is not None else 1000
    return jsonify({
        "done": False,
        "index": idx,
        "total": len(images),
        "filename": path.name,
        "auto_spine": find_auto_spine(str(path)),
        "width": w,
    })


@app.route("/image")
def image():
    images = STATE["images"]
    idx = STATE["current"]
    if idx >= len(images):
        return "", 404
    path = images[idx]
    # Віддаємо стиснуте зображення для швидкого завантаження
    img = cv2.imread(str(path))
    if img is None:
        return "", 404
    # Масштабуємо якщо дуже велике
    h, w = img.shape[:2]
    if w > 2400:
        scale = 2400 / w
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes(), 200, {"Content-Type": "image/jpeg"}


@app.route("/save", methods=["POST"])
def save():
    data = request.get_json()
    spine_x = int(data["spine_x"])
    images = STATE["images"]
    idx = STATE["current"]
    if idx >= len(images):
        return jsonify({"ok": False})

    path = images[idx]
    img = cv2.imread(str(path))
    if img is None:
        return jsonify({"ok": False, "error": "cannot read image"})

    left  = img[:, :spine_x]
    right = img[:, spine_x:]

    out = Path(STATE["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    stem = path.stem
    cv2.imwrite(str(out / f"{stem}_L.jpg"), left,  [cv2.IMWRITE_JPEG_QUALITY, 95])
    cv2.imwrite(str(out / f"{stem}_R.jpg"), right, [cv2.IMWRITE_JPEG_QUALITY, 95])

    STATE["done"].append(path.name)
    STATE["current"] += 1
    print(f"[{idx+1}/{len(images)}] {path.name} → x={spine_x}  ✓")
    return jsonify({"ok": True})


@app.route("/skip", methods=["POST"])
def skip():
    images = STATE["images"]
    idx = STATE["current"]
    if idx < len(images):
        STATE["skipped"].append(images[idx].name)
        print(f"[{idx+1}/{len(images)}] {images[idx].name} → пропущено")
    STATE["current"] += 1
    return jsonify({"ok": True})


def main():
    parser = argparse.ArgumentParser(description="Web-based split tool")
    parser.add_argument("--folder", required=True, help="Тека з розворотами")
    parser.add_argument("--out", default="./split", help="Тека для результатів")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    folder = Path(args.folder)
    images = sorted(
        list(folder.glob("*.jpg")) + list(folder.glob("*.JPG")) +
        list(folder.glob("*.png")) + list(folder.glob("*.PNG"))
    )
    if not images:
        print(f"Зображень не знайдено в {folder}")
        return

    STATE["images"] = images
    STATE["out_dir"] = args.out

    print(f"Знайдено {len(images)} зображень")
    print(f"Результати → {args.out}")
    print(f"\nВідкрий браузер: http://localhost:{args.port}\n")
    print("Керування:")
    print("  Мишею      — провести лінію розрізу")
    print("  ← →        — точне підстроювання по 1px")
    print("  Enter      — зберегти і далі")
    print("  S          — пропустити")

    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
