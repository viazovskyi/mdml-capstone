
import cv2
import csv
import json
from pathlib import Path
from line_detector import extract_page_lines

def extract_line_images(image_path, out_dir, debug=False, crop_top=0):
    """
    Отримує координати рядків від спрощеного pipeline і вирізає їх.
    """
    img_full = cv2.imread(str(image_path))
    if img_full is None:
        return []

    if crop_top > 0:
        img_cropped = img_full[crop_top:, :]
        # Зберігаємо тимчасовий кроп для pipeline
        tmp_path = Path(out_dir) / "_pipeline" / ("_cropped_" + Path(image_path).name)
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(tmp_path), img_cropped)
        src_path = tmp_path
        y_offset = crop_top
    else:
        src_path = image_path
        y_offset = 0

    # Викликаємо нашу нову легку функцію
    page_data = extract_page_lines(src_path)
    if not page_data:
        return []

    img = img_full  # завжди ріжемо з оригіналу
    h, w = img.shape[:2]
    
    x_start = page_data["x_start"]

    lines = []
    idx = 0
    for line in page_data["lines"]:
        y1 = line["y1"] + y_offset
        y2 = line["y2"] + y_offset
        
        if y2 - y1 < 8:  # занадто тонкий — артефакт
            continue

        # Беремо від x_start до самого правого краю (щоб захопити вік)
        cell = img[y1:y2, x_start:w]
        idx += 1
        lines.append({
            "idx": idx,
            "image": cell,
            "y1": y1,
            "y2": y2,
            "height": y2 - y1,
        })

    return lines

def align_lines_to_markup(lines, markup, page_stem):
    """
    Зіставляє вирізані рядки з розміткою.

    Проблема: table_pipeline може знайти N рядків, а в розмітці M рядків.
    Часто N > M бо pipeline знаходить зайві тонкі артефакти (h < 15px).

    Стратегія:
      1. Фільтруємо занадто тонкі рядки (< 12px) — зазвичай це пробіли між рядками
      2. Якщо кількість збігається — зіставляємо 1:1 по порядку
      3. Якщо N > M — пропускаємо найтонші надлишкові рядки
      4. Якщо N < M — деякі рядки розмітки позначаємо як "не знайдено"
    """
    # Фільтр: прибираємо занадто тонкі
    significant = [l for l in lines if l["height"] >= 12]

    n_lines = len(significant)
    n_markup = len(markup)

    print(f"  Рядків pipeline: {len(lines)} → після фільтру: {n_lines}")
    print(f"  Рядків розмітки: {n_markup}")

    if n_lines == n_markup:
        print(f"  Збіг 1:1 ✓")
        return [(significant[i], markup[i]) for i in range(n_lines)]
    else:
        with open("failed_pages.log", "a", encoding="utf-8") as log_file:
            log_file.write(f"{page_stem} | Картинки: {n_lines}, JSON: {n_markup}\n")


    if n_lines > n_markup:
        # Більше рядків ніж розмітки — пропускаємо найтонші надлишкові
        diff = n_lines - n_markup
        print(f"  Pipeline знайшов на {diff} більше — прибираємо найтонші")
        sorted_by_height = sorted(significant, key=lambda l: l["height"])
        to_skip = set(id(l) for l in sorted_by_height[:diff])
        filtered = [l for l in significant if id(l) not in to_skip]
        # Відновлюємо порядок по y1
        filtered.sort(key=lambda l: l["y1"])
        return [(filtered[i], markup[i]) for i in range(min(len(filtered), n_markup))]

    else:
        # Менше рядків ніж розмітки — беремо скільки є
        print(f"  Pipeline знайшов на {n_markup - n_lines} менше — беремо {n_lines}")
        return [(significant[i], markup[i]) for i in range(n_lines)]


def write_csv(all_pairs, out_dir):
    """Додає рядки до labels.csv (append), не перезаписує."""
    out_dir = Path(out_dir)
    csv_path = out_dir / "labels.csv"
    fields = ["file", "text", "type", "page", "line", "height_px"]

    file_exists = csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        writer.writerows(all_pairs)

    # Рахуємо загальну кількість рядків
    with open(csv_path, encoding="utf-8") as f:
        total = sum(1 for _ in f) - 1  # мінус заголовок
    print(f"\nLabels CSV: {csv_path} (+{len(all_pairs)}, всього {total})")
    return csv_path


def write_hf_dataset(all_pairs, out_dir):
    """Додає рядки до metadata.jsonl (append)."""
    out_dir = Path(out_dir)
    jsonl_path = out_dir / "metadata.jsonl"
    with open(jsonl_path, "a", encoding="utf-8") as f:
        for pair in all_pairs:
            f.write(json.dumps({
                "file_name": pair["file"],
                "text": pair["text"],
            }, ensure_ascii=False) + "\n")
    total = sum(1 for _ in open(jsonl_path, encoding="utf-8"))
    print(f"HF metadata: {jsonl_path} (всього {total})")
    return jsonl_path
