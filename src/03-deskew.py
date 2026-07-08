"""
deskew.py — знаходження кута нахилу сторінки через Hough transform і виправлення.

Використання:
    python deskew.py input.jpg               # зберігає input_deskewed.jpg
    python deskew.py input.jpg --show        # також відкриває вікно з результатом
    python deskew.py input.jpg --out out.jpg # задати ім'я вихідного файлу
"""

import cv2
import numpy as np
import argparse
from pathlib import Path


def find_skew_angle(gray: np.ndarray, debug: bool = False) -> float:
    """
    Знаходить кут нахилу тексту через HoughLinesP.

    Алгоритм:
    1. Розмиття → Canny edges → HoughLinesP (знаходить відрізки)
    2. Для кожного відрізка рахуємо кут у градусах
    3. Залишаємо тільки близькі до горизонталі (±30°) — це рядки тексту
    4. Медіана кутів = кут нахилу сторінки
    """

    # --- Крок 1: підсилення контрасту (важливо для блідих рукописів) ---
    # CLAHE = Contrast Limited Adaptive Histogram Equalization
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # --- Крок 2: розмиття щоб прибрати дрібний шум ---
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)

    # --- Крок 3: Canny — знаходимо краї ---
    edges = cv2.Canny(blurred, threshold1=50, threshold2=150, apertureSize=3)

    # --- Крок 4: HoughLinesP — знаходимо відрізки на краях ---
    # minLineLength=100  — ігноруємо короткі шуми (букви, плями)
    # maxLineGap=20      — з'єднуємо близькі відрізки в один
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=100,
        minLineLength=100,
        maxLineGap=20,
    )

    if lines is None:
        print("  [!] Hough не знайшов ліній, кут = 0°")
        return 0.0

    # --- Крок 5: рахуємо кут кожного відрізка ---
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        if x2 == x1:
            continue  # вертикальна лінія — пропускаємо
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # Залишаємо тільки "горизонтальні" лінії (рядки тексту або лінійки таблиці)
        if -30 < angle < 30:
            angles.append(angle)

    if not angles:
        print("  [!] Немає придатних кутів, кут = 0°")
        return 0.0

    # Медіана надійніша за середнє — не боїться викидів
    skew_angle = float(np.median(angles))

    if debug:
        print(f"  Знайдено {len(lines)} ліній, придатних для кута: {len(angles)}")
        print(f"  Кути (вибірка): {sorted(angles)[:10]}")
        print(f"  Медіана кута: {skew_angle:.2f}°")

    return skew_angle


def rotate_image(image: np.ndarray, angle: float) -> np.ndarray:
    """
    Повертає зображення на заданий кут навколо центру.
    Фон заповнюється білим (255) — підходить для документів.
    """
    h, w = image.shape[:2]
    center = (w // 2, h // 2)

    # Матриця афінного перетворення для повороту
    M = cv2.getRotationMatrix2D(center, angle, scale=1.0)

    # warpAffine застосовує матрицю до всього зображення
    rotated = cv2.warpAffine(
        image,
        M,
        (w, h),
        flags=cv2.INTER_CUBIC,          # якісна інтерполяція
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),    # білий фон
    )
    return rotated


def deskew(image_path: str, output_path: str = None, show: bool = False, debug: bool = False):
    """Головна функція: завантажує, виправляє нахил, зберігає."""

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Не вдалось завантажити: {image_path}")

    print(f"Завантажено: {image_path}  ({img.shape[1]}×{img.shape[0]} px)")

    # Переводимо в сірий для аналізу (оригінал кольоровий зберігаємо окремо)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Знаходимо кут
    angle = find_skew_angle(gray, debug=debug)
    print(f"Кут нахилу: {angle:.2f}°")

    # Якщо кут менше 0.5° — не варто крутити, артефакти будуть більше ніж виграш
    if abs(angle) < 0.5:
        print("Кут занадто малий, пропускаємо поворот.")
        corrected = img
    else:
        corrected = rotate_image(img, angle)
        print(f"Повернуто на {-angle:.2f}°")

    # Зберігаємо
    if output_path is None:
        p = Path(image_path)
        output_path = str(p.parent / (p.stem + "_deskewed" + p.suffix))

    cv2.imwrite(output_path, corrected)
    print(f"Збережено: {output_path}")

    if show:
        # Показуємо до/після поруч
        h = max(img.shape[0], corrected.shape[0])
        comparison = np.ones((h, img.shape[1] + corrected.shape[1] + 10, 3), dtype=np.uint8) * 200
        comparison[:img.shape[0], :img.shape[1]] = img
        comparison[:corrected.shape[0], img.shape[1] + 10:] = corrected
        cv2.imshow("До (ліво) | Після (право)", comparison)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return angle, corrected


# ── Пакетна обробка теки ────────────────────────────────────────────────────

def process_folder(folder: str, debug: bool = False):
    """Обробляє всі .jpg/.png в теці, зберігає поруч з суфіксом _deskewed."""
    folder = Path(folder)
    images = list(folder.glob("*.jpg")) + list(folder.glob("*.JPG")) + \
             list(folder.glob("*.png")) + list(folder.glob("*.PNG"))

    if not images:
        print(f"Зображень не знайдено в {folder}")
        return

    print(f"Знайдено {len(images)} зображень у {folder}\n")
    for i, img_path in enumerate(sorted(images), 1):
        print(f"[{i}/{len(images)}] {img_path.name}")
        try:
            angle, _ = deskew(str(img_path), debug=debug)
        except Exception as e:
            print(f"  Помилка: {e}")
        print()


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deskew document image via Hough transform")
    parser.add_argument("input", help="Шлях до зображення або теки")
    parser.add_argument("--out", default=None, help="Вихідний файл (за замовчуванням: *_deskewed.*)")
    parser.add_argument("--show", action="store_true", help="Показати порівняння до/після")
    parser.add_argument("--debug", action="store_true", help="Детальний вивід кутів")
    parser.add_argument("--folder", action="store_true", help="Обробити всю теку")
    args = parser.parse_args()

    if args.folder or Path(args.input).is_dir():
        process_folder(args.input, debug=args.debug)
    else:
        deskew(args.input, output_path=args.out, show=args.show, debug=args.debug)
