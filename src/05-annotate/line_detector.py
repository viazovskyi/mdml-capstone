

import cv2
import numpy as np
import argparse
import json
import os
from pathlib import Path
from collections import defaultdict
from scipy.signal import find_peaks
from scipy.ndimage import maximum_filter1d


# ═══════════════════════════════════════════════════════════════
# 2. DETECT ROW SEPARATORS (drawn horizontal lines + dashes)
# ═══════════════════════════════════════════════════════════════

def detect_row_separators(gray, score_threshold=8, min_span_ratio=0.5):
    """
    Find horizontal row separators using run-length analysis.
    Detects both solid lines and dashed lines ("— — — —").
    """
    h, w = gray.shape
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    x_start = int(w * 0.15)
    x_end = int(w * 0.95)
    scan_w = x_end - x_start

    scores = np.zeros(h)
    for y in range(h):
        row = binary[y, x_start:x_end]
        if np.sum(row) == 0:
            continue

        padded = np.concatenate([[0], row, [0]])
        diff = np.diff(padded.astype(int))
        starts = np.where(diff > 0)[0]
        ends = np.where(diff < 0)[0]
        if len(starts) == 0:
            continue

        run_lengths = ends - starts
        short_mask = (run_lengths >= 3) & (run_lengths <= 25)
        short_runs = run_lengths[short_mask]

        if len(short_runs) >= 5:
            positions = [
                (starts[i] + ends[i]) // 2
                for i in range(len(starts))
                if short_mask[i]
            ]
            if len(positions) >= 5:
                span = max(positions) - min(positions)
                if span > scan_w * min_span_ratio:
                    scores[y] = len(short_runs) * (span / scan_w)

    scores_smooth = maximum_filter1d(scores, size=3)
    peaks, _ = find_peaks(
        scores_smooth, height=score_threshold,
        distance=10, prominence=3
    )

    return sorted([int(p) for p in peaks])


def find_text_lines(gray_region, text_x1=None, text_x2=None, min_line_height=8):
    """
    Split a row region into individual text lines via valley-based projection.

    КРИТИЧНО: проекцію треба рахувати ТІЛЬКИ по текстовій зоні (колонка "опис"),
    а не по всій ширині рядка. Якщо рахувати по всій ширині, темний корінець
    зліва і вертикальні лінії колонок справа ніколи не дають проекції впасти
    до нуля між рядками — тому весь блок завжди визначався як один суцільний
    текстовий рядок (саме цей баг і блокував розбиття R6/R7/R8).

    Метод: замість порогу (threshold) шукаємо локальні МІНІМУМИ (valleys)
    у згладженій проекції — це міжрядкові проміжки. Адаптується до
    нерівномірної щільності тексту краще за глобальний поріг.
    """
    h_r, w_r = gray_region.shape
    if h_r < min_line_height * 2:
        return [(0, h_r)]

    # Текстова зона за замовчуванням: 8%..50% ширини
    # (пропускає темний корінець зліва, не зачіпає лінії колонок справа)
    if text_x1 is None:
        text_x1 = int(w_r * 0.08)
    if text_x2 is None:
        text_x2 = int(w_r * 0.50)
    text_x1 = max(0, min(text_x1, w_r - 1))
    text_x2 = max(text_x1 + 1, min(text_x2, w_r))

    text_zone = gray_region[:, text_x1:text_x2]
    _, bw = cv2.threshold(
        text_zone, 0, 255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    proj = np.sum(bw, axis=1).astype(float) / 255
    k = max(3, h_r // 40)
    proj_smooth = np.convolve(proj, np.ones(k) / k, mode="same")

    if proj_smooth.max() < 1:
        return [(0, h_r)]

    inverted = proj_smooth.max() - proj_smooth
    valleys, _ = find_peaks(
        inverted, distance=max(6, min_line_height),
        prominence=proj_smooth.max() * 0.12
    )

    cut_points = [0] + sorted(int(v) for v in valleys) + [h_r]
    cleaned = [cut_points[0]]
    for c in cut_points[1:]:
        if c - cleaned[-1] >= min_line_height:
            cleaned.append(c)
    if cleaned[-1] != h_r:
        cleaned[-1] = h_r

    lines = []
    for i in range(len(cleaned) - 1):
        s, e = cleaned[i], cleaned[i + 1]
        if e - s >= min_line_height:
            lines.append((s, e))

    return lines if lines else [(0, h_r)]


def extract_page_lines(image_path):
    """
    Спрощена логіка: знаходить лише горизонтальні координати рядків.
    Нічого не зберігає на диск. Повертає словник з координатами.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return None
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = img.shape[:2]

    # Замість складного пошуку колонок просто беремо відступи
    x_start = int(w * 0.08)  # Відступ від корінця (8% зліва)
    text_x2 = int(w * 0.50)  # Де закінчується текст для аналізу проміжків

    # 1. Шукаємо великі розділювачі (тирки)
    row_seps = detect_row_separators(gray)
    row_boundaries = [0] + row_seps + [h]

    lines_coords = []

    # 2. Шукаємо підрядки
    for ri in range(len(row_boundaries) - 1):
        ry1, ry2 = row_boundaries[ri], row_boundaries[ri + 1]
        if ry2 - ry1 < 5:
            continue

        row_gray = gray[ry1:ry2, :]
        text_lines = find_text_lines(row_gray, text_x1=x_start, text_x2=text_x2)

        for sy1, sy2 in text_lines:
            abs_y1 = ry1 + sy1
            abs_y2 = ry1 + sy2
            lines_coords.append({
                "y1": int(abs_y1), 
                "y2": int(abs_y2)
            })

    # Повертаємо загальний відступ X та список Y-координат
    return {
        "x_start": x_start, 
        "lines": lines_coords
    }

