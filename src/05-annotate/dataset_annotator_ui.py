import cv2
import csv
import json
import argparse
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from dataset_utils import extract_line_images, align_lines_to_markup, write_csv, write_hf_dataset

class DatasetAnnotationApp:
    def __init__(self, root, img_path, pairs, out_dir, page_stem):
        self.root = root
        self.img_path = Path(img_path)
        self.out_dir = Path(out_dir)
        self.page_stem = page_stem
        self.saved_successfully = False
        
        self.cv_img = cv2.imread(str(img_path))
        self.img_h, self.img_w = self.cv_img.shape[:2]
        
        self.lines_y = []
        self.markup_items = []
        
        for line_data, markup_item in pairs:
            text = markup_item["text"].strip()
            if markup_item.get("numbers"):
                nums_str = "  ".join(markup_item["numbers"])
                text_full = f"{text}  {nums_str}"
            else:
                text_full = text
                
            self.lines_y.append(line_data["y2"])
            self.markup_items.append({
                "text": text_full,
                "type": markup_item.get("type", "")
            })
            
        self.lines_y.sort()
        self.start_y = pairs[0][0]["y1"] if pairs else 0
        self.dragged_line_idx = None
        
        self.setup_ui()
        self.enable_universal_copy_paste()
        
    def setup_ui(self):
        self.root.title(f"Валідація нарізки: {self.img_path.name}")
        self.root.geometry("1600x950")
        
        style = ttk.Style()
        style.configure("Green.TButton", font=("Arial", 11, "bold"), foreground="black", background="#10b981")
        style.configure("Red.TButton", font=("Arial", 11, "bold"), foreground="black", background="#ef4444")
        style.configure("Action.TButton", font=("Arial", 10, "bold"), width=3)
        
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)
        
        # ЛІВА ЧАСТИНА: Зображення
        canvas_frame = ttk.Frame(main_paned)
        main_paned.add(canvas_frame, weight=2)
        
        self.canvas = tk.Canvas(canvas_frame, bg="#1e1e1e", cursor="cross")
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # ПРАВА ЧАСТИНА: Елементи керування
        control_frame = ttk.Frame(main_paned, padding=15)
        main_paned.add(control_frame, weight=2)
        
        top_info_frame = ttk.Frame(control_frame)
        top_info_frame.pack(side=tk.TOP, fill=tk.X)
        
        lbl = ttk.Label(top_info_frame, text=f"Файл: {self.img_path.name}", font=("Arial", 12, "bold"))
        lbl.pack(anchor=tk.W, pady=2)
        
        lbl_hint = ttk.Label(top_info_frame, text="• ЛКМ + Тягнути: рухати лінію.  • Ctrl + ЛКМ: додати лінію.  • Правий Клік: видалити лінію.\n• Кнопки [+] та [X] зліва регулюють маркап.", font=("Arial", 10))
        lbl_hint.pack(anchor=tk.W, pady=5)
        
        # Кнопки дії зафіксовані в самому низу
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        
        btn_skip = ttk.Button(btn_frame, text="⏭️ Пропустити сторінку", style="Red.TButton", command=self.root.destroy)
        btn_skip.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, ipady=10)
        
        btn_save = ttk.Button(btn_frame, text="💾 Зберегти та нарізати", style="Green.TButton", command=self.save_and_close)
        btn_save.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5, ipady=10)
        
        # Скрол-зона для інпутів
        self.scroll_canvas = tk.Canvas(control_frame, borderwidth=0)
        inputs_scroll = ttk.Scrollbar(control_frame, orient=tk.VERTICAL, command=self.scroll_canvas.yview)
        self.inputs_frame = ttk.Frame(self.scroll_canvas)
        
        self.inputs_frame.bind("<Configure>", lambda e: self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all")))
        self.scroll_canvas_window = self.scroll_canvas.create_window((0, 0), window=self.inputs_frame, anchor="nw")
        self.scroll_canvas.configure(yscrollcommand=inputs_scroll.set)
        
        self.scroll_canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        
        inputs_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.scroll_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        control_frame.bind("<Configure>", self.on_control_frame_resize)
        
        # Малюємо картинку
        self.pil_img = Image.open(self.img_path)
        self.tk_img = ImageTk.PhotoImage(self.pil_img)
        self.canvas.create_image(0, 0, image=self.tk_img, anchor=tk.NW)
        self.canvas.config(scrollregion=(0, 0, self.img_w, self.img_h))
        
        self.text_vars = []
        
        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right_click)
        
        self.render_lines_and_inputs()
        
    def enable_universal_copy_paste(self):
        self.root.bind_all("<Control-KeyPress>", self.handle_ctrl_shortcuts)

    def handle_ctrl_shortcuts(self, event):
        # 86 = V (Вставка)
        if event.keycode == 86:
            event.widget.event_generate("<<Paste>>")
            return "break"  # <--- ЦЕЙ РЯДОК ЗУПИНЯЄ ДУБЛЮВАННЯ!
        
        # 67 = C (Копіювання)
        elif event.keycode == 67:
            event.widget.event_generate("<<Copy>>")
            return "break"
        
        # 88 = X (Вирізання)
        elif event.keycode == 88:
            event.widget.event_generate("<<Cut>>")
            return "break"
        
        # 65 = A (Виділити все)
        elif event.keycode == 65:
            if hasattr(event.widget, 'selection_range'):
                event.widget.selection_range(0, tk.END)
                return "break"

    def on_control_frame_resize(self, event):
        canvas_width = event.width - 30
        self.scroll_canvas.itemconfig(self.scroll_canvas_window, width=canvas_width)

    def on_mousewheel(self, event):
        self.scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def sync_inputs_to_markup(self):
        for idx, t_var in enumerate(self.text_vars):
            if idx < len(self.markup_items):
                self.markup_items[idx]["text"] = t_var.get()

    def render_lines_and_inputs(self):
        self.sync_inputs_to_markup()

        self.canvas.delete("overlay")
        for widget in self.inputs_frame.winfo_children():
            widget.destroy()
        self.text_vars.clear()
        
        # 1. Малюємо лінії та перераховуємо мітки на картинці по порядку
        for idx, y in enumerate(self.lines_y):
            self.canvas.create_line(0, y, self.img_w, y, fill="#ef4444", width=2, tags=("overlay", f"line_{idx}"))
            prev_y = self.lines_y[idx - 1] if idx > 0 else self.start_y
            text_pos_y = prev_y + (y - prev_y) // 2 - 7
            self.canvas.create_text(20, text_pos_y, text=f"L{idx + 1}", fill="#d34e34", anchor=tk.NW, tags="overlay", font=("Arial", 11, "bold"))

        # Остання мітка під останньою лінією
        if self.lines_y:
            self.canvas.create_text(20, self.lines_y[-1] + 15, text=f"L{len(self.lines_y) + 1}", fill="#d34e34", anchor=tk.NW, tags="overlay", font=("Arial", 11, "bold"))

        # 2. Рендеримо рядки праворуч із ПРАВИЛЬНИМИ порядковими номерами
        for idx, item in enumerate(self.markup_items):
            main_row_frame = ttk.Frame(self.inputs_frame, padding=2)
            main_row_frame.pack(fill=tk.X, expand=True, pady=5)
            
            left_controls = ttk.Frame(main_row_frame)
            left_controls.pack(side=tk.LEFT, padx=5)
            
            # Номер рядка тепер динамічний (idx + 1)
            lbl_item = ttk.Label(left_controls, text=f"Рядок {idx + 1}:", font=("Arial", 10, "bold"), width=12)
            lbl_item.pack(side=tk.LEFT)
            
            btn_add_text = ttk.Button(left_controls, text="+", style="Action.TButton", command=lambda i=idx: self.add_text_row(i))
            btn_add_text.pack(side=tk.LEFT, padx=1)
            
            btn_del_text = ttk.Button(left_controls, text="X", style="Action.TButton", command=lambda i=idx: self.remove_text_row(i))
            btn_del_text.pack(side=tk.LEFT, padx=1)
            
            t_var = tk.StringVar(value=item["text"])
            self.text_vars.append(t_var)
            
            entry = ttk.Entry(main_row_frame, textvariable=t_var, font=("Arial", 14))
            entry.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5)
            
    def add_text_row(self, index):
        self.sync_inputs_to_markup()
        new_item = {"text": "", "type": ""}
        self.markup_items.insert(index + 1, new_item)
        self.render_lines_and_inputs()
        
    def remove_text_row(self, index):
        self.sync_inputs_to_markup()
        if not self.markup_items:
            return
        self.markup_items.pop(index)
        self.render_lines_and_inputs()

    def on_left_click(self, event):
        canvas_y = self.canvas.canvasy(event.y)
        
        if event.state & 0x0004:  # Ctrl + ЛКМ
            click_y = int(canvas_y)
            click_y = max(0, min(click_y, self.img_h))
            
            self.lines_y.append(click_y)
            self.lines_y.sort()
            
            insert_idx = self.lines_y.index(click_y)
            new_item = {"text": "", "type": ""}
            self.markup_items.insert(insert_idx, new_item)
            
            self.render_lines_and_inputs()
            return

        for idx, y in enumerate(self.lines_y):
            if abs(canvas_y - y) <= 8:
                self.dragged_line_idx = idx
                return

    def on_drag(self, event):
        if self.dragged_line_idx is None:
            return
        canvas_y = int(self.canvas.canvasy(event.y))
        canvas_y = max(0, min(canvas_y, self.img_h))
        
        idx = self.dragged_line_idx
        self.lines_y[idx] = canvas_y
        self.canvas.coords(f"line_{idx}", 0, canvas_y, self.img_w, canvas_y)
        
        # Динамічно оновлюємо мітки під час перетягування
        self.canvas.delete("overlay")
        for i, y in enumerate(self.lines_y):
            self.canvas.create_line(0, y, self.img_w, y, fill="#ef4444", width=2, tags=("overlay", f"line_{i}"))
            prev_y = self.lines_y[i - 1] if i > 0 else self.start_y
            text_pos_y = prev_y + (y - prev_y) // 2 - 7
            self.canvas.create_text(20, text_pos_y, text=f"L{i + 1}", fill="#d34e34", anchor=tk.NW, tags="overlay", font=("Arial", 11, "bold"))
        if self.lines_y:
            self.canvas.create_text(20, self.lines_y[-1] + 15, text=f"L{len(self.lines_y) + 1}", fill="#d34e34", anchor=tk.NW, tags="overlay", font=("Arial", 11, "bold"))

    def on_release(self, event):
        self.dragged_line_idx = None
        self.lines_y.sort()

    def on_right_click(self, event):
        if not self.lines_y:
            return
        canvas_y = self.canvas.canvasy(event.y)
        closest_idx = min(range(len(self.lines_y)), key=lambda i: abs(self.lines_y[i] - canvas_y))
        
        if abs(self.lines_y[closest_idx] - canvas_y) <= 40:
            self.lines_y.pop(closest_idx)
            if closest_idx < len(self.markup_items):
                self.markup_items.pop(closest_idx)
            self.render_lines_and_inputs()

    def save_and_close(self):
        self.sync_inputs_to_markup()
            
        self.final_saved_data = []
        images_dir = self.out_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, item in enumerate(self.markup_items):
            y1 = self.lines_y[idx - 1] if idx > 0 else self.start_y
            y2 = self.lines_y[idx] if idx < len(self.lines_y) else self.img_h
            
            if y2 <= y1:
                continue
            
            cell = self.cv_img[y1:y2, 0:self.img_w]
            fname = f"{self.page_stem}_line{idx + 1:03d}.jpg"
            
            fpath = images_dir / fname
            cv2.imwrite(str(fpath), cell, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            self.final_saved_data.append({
                "file": str(fpath.relative_to(self.out_dir)),
                "text": item["text"],
                "type": "",
                "page": self.page_stem,
                "line": idx + 1,
                "height_px": y2 - y1,
            })
        self.saved_successfully = True
        self.root.destroy()

def process_single_image(img_path, markup_path, out_dir, crop_top):
    img_path = Path(img_path)
    markup_path = Path(markup_path)
    page_stem = img_path.stem
    
    print(f"\n[Обробка сторінки: {img_path.name}]")
    
    with open(markup_path, encoding="utf-8") as f:
        markup = json.load(f)
    markup_filtered = [m for m in markup if m.get("type") != "separator"]
    
    lines = extract_line_images(img_path, out_dir, debug=False, crop_top=crop_top)
    if not lines:
        print(f"  Не вдалося вирізати початкові лінії для {img_path.name}")
        return
        
    pairs = align_lines_to_markup(lines, markup_filtered, page_stem)
    if not pairs:
        return

    root = tk.Tk()
    app = DatasetAnnotationApp(root, img_path, pairs, out_dir, page_stem)
    root.mainloop()
    
    if app.saved_successfully and app.final_saved_data:
        write_csv(app.final_saved_data, out_dir)
        write_hf_dataset(app.final_saved_data, out_dir)
        print(f"  ✓ Сторінку {img_path.name} успішно збережено.")
    else:
        print(f"  ⏭️ Сторінку {img_path.name} пропущено користувачем.")

def main():
    parser = argparse.ArgumentParser(description="Інтерактивна пакетна збірка датасету TrOCR")
    parser.add_argument("input", help="Зображення або папка з зображеннями")
    parser.add_argument("--markup", default=None, help="JSON розмітка (для одного файлу)")
    parser.add_argument("--markups", default=None, help="Папка з JSON розмітками (пакетний режим)")
    parser.add_argument("--out", default="./dataset", help="Вихідна тека датасету")
    parser.add_argument("--crop-top", type=int, default=0, help="Відрізати N пікселів зверху")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    input_path = Path(args.input)
    
    if input_path.is_dir():
        markups_dir = Path(args.markups) if args.markups else input_path
        images = sorted(list(input_path.glob("*.jpg")) + list(input_path.glob("*.png")))
        images = [p for p in images if "_debug" not in p.stem]
        
        print(f"Знайдено {len(images)} зображень в папці.")
        for img_path in images:
            markup_path = markups_dir / (img_path.stem + ".json")
            if not markup_path.exists():
                print(f"Пропускаємо {img_path.name} — немає розмітки {markup_path.name}")
                continue
            process_single_image(img_path, markup_path, out_dir, args.crop_top)
    else:
        if not args.markup:
            print("ПОМИЛКА: вкажи --markup шлях до JSON розмітки")
            return
        process_single_image(input_path, args.markup, out_dir, args.crop_top)
        
    print("\nПакетна обробка завершена!")

if __name__ == "__main__":
    main()