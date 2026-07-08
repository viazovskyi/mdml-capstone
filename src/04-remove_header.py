import os
import json
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

class DocumentCleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Semi-Auto Header Remover")
        
        # Directories
        self.in_img_dir = "input/images"
        self.in_json_dir = "input/json"
        self.out_img_dir = "output/images"
        self.out_json_dir = "output/json"
        
        os.makedirs(self.out_img_dir, exist_ok=True)
        os.makedirs(self.out_json_dir, exist_ok=True)
        
        # Load file list
        self.image_files = sorted([f for f in os.listdir(self.in_img_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
        self.current_index = 0
        
        self.current_img = None
        self.crop_y_original = 0
        self.scale_ratio = 1.0
        
        self.setup_ui()
        self.load_current_file()
        
        self.root.bind('<Return>', lambda event: self.save_and_next())
        self.root.bind('<Escape>', lambda event: self.skip_file())
        self.root.bind('<Left>', lambda event: self.prev_file())
        self.root.bind('<Right>', lambda event: self.next_file())

    def prev_file(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_file()

    def next_file(self):
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.load_current_file()
    def skip_file(self):
        # Move to the next file without saving any images or JSON
        self.current_index += 1
        self.load_current_file()

    def setup_ui(self):
        # Left frame: Image and Canvas
        self.left_frame = tk.Frame(self.root)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.left_frame, cursor="crosshair", bg="gray")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.set_crop_line)
        
        # Right frame: JSON Data and Controls
        self.right_frame = tk.Frame(self.root, width=400)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        
        tk.Label(self.right_frame, text="Select lines to KEEP:", font=("Arial", 12, "bold")).pack(pady=5)
        
        # Створюємо контейнер для скролу
        self.scroll_container = tk.Frame(self.right_frame)
        self.scroll_container.pack(fill=tk.BOTH, expand=True, pady=5)

        # Додаємо Canvas (полотно) та Scrollbar (повзунок)
        self.canvas_scroll = tk.Canvas(self.scroll_container, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.scroll_container, orient="vertical", command=self.canvas_scroll.yview)
        
        # Це той самий check_frame, але тепер він всередині Canvas
        self.check_frame = tk.Frame(self.canvas_scroll)

        # Прив'язуємо розмір фрейму до зони прокрутки
        self.check_frame.bind(
            "<Configure>",
            lambda e: self.canvas_scroll.configure(
                scrollregion=self.canvas_scroll.bbox("all")
            )
        )

        # Створюємо вікно всередині Canvas
        self.canvas_scroll.create_window((0, 0), window=self.check_frame, anchor="nw")
        self.canvas_scroll.configure(yscrollcommand=self.scrollbar.set)

        # Розміщуємо Canvas і Scrollbar
        self.canvas_scroll.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Додаємо прокрутку коліщатком мишки (дуже зручно на Windows)
        def _on_mousewheel(event):
            self.canvas_scroll.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas_scroll.bind_all("<MouseWheel>", _on_mousewheel)
        
        self.json_vars = []
        self.json_data = []
        
        # Buttons
        self.btn_frame = tk.Frame(self.right_frame)
        self.btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        
        self.btn_save = tk.Button(self.btn_frame, text="Save & Next", command=self.save_and_next, bg="green", fg="white", font=("Arial", 12))
        self.btn_save.pack(fill=tk.X)


    def load_current_file(self):
        if self.current_index >= len(self.image_files):
            messagebox.showinfo("Done", "All files processed!")
            self.root.quit()
            return

        img_name = self.image_files[self.current_index]
        base_name = os.path.splitext(img_name)[0]
        
        # 1. Формуємо шляхи для оригіналів (з папки input)
        in_img_path = os.path.join(self.in_img_dir, img_name)
        json_name = base_name.replace("source_", "").replace("_deskewed", "_markup") + ".json"
        in_json_path = os.path.join(self.in_json_dir, json_name)

        # 2. Формуємо шляхи для результатів (з папки output)
        out_json_name = base_name + ".json"
        out_img_path = os.path.join(self.out_img_dir, img_name)
        out_json_path = os.path.join(self.out_json_dir, out_json_name)

        # 3. ПЕРЕВІРКА: чи є файл вже в папці output?
        if os.path.exists(out_img_path) and os.path.exists(out_json_path):
            img_path = out_img_path
            json_path = out_json_path
            status_text = "[ВЖЕ ОБРОБЛЕНО]"
        else:
            img_path = in_img_path
            json_path = in_json_path
            status_text = "[ОРИГІНАЛ]"

        self.root.title(f"Processing: {img_name} ({self.current_index + 1}/{len(self.image_files)}) {status_text}")

        # Завантаження картинки
        self.original_img = Image.open(img_path)
        orig_w, orig_h = self.original_img.size
        
        # Отримуємо реальну висоту вашого екрану
        screen_height = self.root.winfo_screenheight()
        
        # Беремо висоту екрану мінус 150 пікселів (запас на панель "Пуск" і рамку вікна)
        display_h = screen_height - 150
        
        # Якщо картинка від самого початку менша за екран, не розтягуємо її
        if orig_h < display_h:
            display_h = orig_h
            
        self.scale_ratio = display_h / orig_h
        display_w = int(orig_w * self.scale_ratio)
        
        self.display_img = self.original_img.resize((display_w, display_h), Image.Resampling.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(self.display_img)
        
        self.canvas.config(width=display_w, height=display_h)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_img)
        
        self.crop_y_original = 0
        self.canvas.delete("crop_line")

        # Завантаження JSON
        for widget in self.check_frame.winfo_children():
            widget.destroy()
            
        self.json_vars = []
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)
                
            for item in self.json_data:
                var = tk.BooleanVar(value=True) 
                self.json_vars.append(var)
                
                preview_text = f"Line {item.get('line', '?')}: {item.get('text', '')[:40]}..."
                cb = tk.Checkbutton(self.check_frame, text=preview_text, variable=var, anchor="w")
                cb.pack(fill=tk.X)
        else:
            self.json_data = []
            tk.Label(self.check_frame, text="No matching JSON found!").pack()

    def load_current_file_(self):
        if self.current_index >= len(self.image_files):
            messagebox.showinfo("Done", "All files processed!")
            self.root.quit()
            return

        img_name = self.image_files[self.current_index]
        base_name = os.path.splitext(img_name)[0]
        
        json_name = base_name.replace("source_", "").replace("_deskewed", "_markup") + ".json"
        #json_name = base_name + ".json" 
        
        img_path = os.path.join(self.in_img_dir, img_name)
        json_path = os.path.join(self.in_json_dir, json_name)
        
        if not os.path.exists(json_path):
            # Fallback to _markup.json based on your example
            json_name = base_name.replace("_deskewed", "_markup") + ".json"
            json_path = os.path.join(self.in_json_dir, json_name)

        self.root.title(f"Processing: {img_name} ({self.current_index + 1}/{len(self.image_files)})")

        # Load and scale image for UI
        self.original_img = Image.open(img_path)
        orig_w, orig_h = self.original_img.size
        
        # Scale to fit standard screen height (e.g., 800px)
        display_h = 800
        self.scale_ratio = display_h / orig_h
        display_w = int(orig_w * self.scale_ratio)
        
        self.display_img = self.original_img.resize((display_w, display_h), Image.Resampling.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(self.display_img)
        
        self.canvas.config(width=display_w, height=display_h)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_img)
        
        # Reset crop line
        self.crop_y_original = 0
        self.canvas.delete("crop_line")

        # Load JSON
        for widget in self.check_frame.winfo_children():
            widget.destroy()
            
        self.json_vars = []
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)
                
            for item in self.json_data:
                var = tk.BooleanVar(value=True) # Checked by default
                self.json_vars.append(var)
                
                # Truncate text for UI preview
                preview_text = f"Line {item.get('line', '?')}: {item.get('text', '')[:40]}..."
                cb = tk.Checkbutton(self.check_frame, text=preview_text, variable=var, anchor="w")
                cb.pack(fill=tk.X)
        else:
            self.json_data = []
            tk.Label(self.check_frame, text="No matching JSON found!").pack()

    def set_crop_line(self, event):
        # Draw visual line on canvas
        self.canvas.delete("crop_line")
        y = event.y
        self.canvas.create_line(0, y, self.canvas.winfo_width(), y, fill="red", width=2, tags="crop_line")
        
        # Calculate actual Y coordinate for the original image crop
        self.crop_y_original = int(y / self.scale_ratio)

    def save_and_next(self):
        img_name = self.image_files[self.current_index]
        base_name = os.path.splitext(img_name)[0]
        
        # 1. Crop and Save Image
        if self.crop_y_original > 0:
            width, height = self.original_img.size
            cropped_img = self.original_img.crop((0, self.crop_y_original, width, height))
            cropped_img.save(os.path.join(self.out_img_dir, img_name))
        else:
            # If no line was clicked, just copy the original
            self.original_img.save(os.path.join(self.out_img_dir, img_name))

        # 2. Filter and Save JSON
        filtered_json = []
        for i, item in enumerate(self.json_data):
            if self.json_vars[i].get(): # If checkbox is ticked
                filtered_json.append(item)
                
        # Optional: Re-index line numbers if you want them sequential again
        for idx, item in enumerate(filtered_json, start=1):
            item["line"] = idx

        json_out_name = base_name + ".json"
        with open(os.path.join(self.out_json_dir, json_out_name), "w", encoding="utf-8") as f:
            f.write("[\n")
            f.write(",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in filtered_json))
            f.write("\n]")

        #json_out_name = base_name + ".json"
        #with open(os.path.join(self.out_json_dir, json_out_name), 'w', encoding='utf-8') as f:
        #    json.dump(filtered_json, f, ensure_ascii=False, indent=2)

        # 3. Advance to next
        self.current_index += 1
        self.load_current_file()

if __name__ == "__main__":
    root = tk.Tk()
    app = DocumentCleanerApp(root)
    root.mainloop()