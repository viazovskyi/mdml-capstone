# Handwritten Text Recognition for Revision Lists (Ревізькі казки)

**Capstone project — Advanced Deep Learning for AI Applications**

## Overview

This project builds a full pipeline that reads scanned 18th–19th century russian imperial census documents ("ревізькі казки" / revision lists) — historical, handwritten genealogical records used to reconstruct family trees — and automatically transcribes them into machine-readable text using a fine-tuned Handwritten Text Recognition (HTR) model.

The motivation came from seeing a friend's family tree, built in part from these archival documents. Digitized scans of such records exist in state archives, but no open HTR model is available for pre-reform (pre-1918 orthography) handwritten russian — the old alphabet includes letters no longer in use (ѣ, і, ъ, ѳ, ѕ) and no off-the-shelf tokenizer/model handles it out of the box. This project trains a custom model to fill that gap, as a first step toward automatically extracting names, ages, and family relationships and building a genealogical graph.

**Task type:** Handwritten Text Recognition (sequence-to-sequence, image → text), a text-processing/OCR task within the course scope.

## Pipeline

```
Raw PDF scans
   │
   ▼
1. Split PDF → page images                (01-split_pdf.py)
   │
   ▼
2. Manual page-spread splitting            (02-manual_split_web.py)
   Split each two-page spread scan into left/right single pages
   │
   ▼
3. Deskew                                  (03-deskew.py)
   Hough-transform-based skew angle detection + rotation correction
   │
   ▼
4. Header/margin removal                   (04-remove_header.py)
   Semi-automatic cropping tool (Tkinter) to remove scanner artifacts/headers
   │
   ▼
5. Dataset annotation                      (05-annotate/)
   Row detection + manual line-level transcription UI → labels.csv / metadata.jsonl
   │
   ▼
6. HTR model fine-tuning                   (06-trocr_train.ipynb)
   Fine-tune a TrOCR model on the annotated line-image / text pairs
```

### 1. PDF splitting (`01-split_pdf.py`)
Converts the source PDF into per-page PNG images using `pdf2image`, batching 10 pages at a time to keep memory usage bounded.

### 2. Manual spread splitting (`02-manual_split_web.py`)
Each archive scan is a two-page spread. A small Flask web tool (`localhost:5000`) lets you draw the split line and export the left (`_L`) and right (`_R`) page halves.

### 3. Deskew (`03-deskew.py`)
Detects the page's rotation angle via CLAHE contrast enhancement → Canny edge detection → `HoughLinesP`, keeping only near-horizontal line segments (±30°) and using their median angle to correct skew.

### 4. Header removal (`04-remove_header.py`)
A Tkinter GUI for semi-automatically cropping out table headers/scanner borders from each page image, keeping image/JSON metadata in sync between an `input/` and `output/` folder pair.

### 5. Dataset annotation (`05-annotate/`)
- `line_detector.py` — detects horizontal row separators in the ledger tables (solid and dashed lines) using run-length analysis on the binarized image, to segment each page into text rows.
- `dataset_utils.py` — cuts out row line-images based on detected separators, aligns them against a page's manual text markup (handles mismatches between detected rows and markup entries), and appends results to `labels.csv` (columns: `file, text, type, page, line, height_px`) and a Hugging Face–style `metadata.jsonl`.
- `dataset_annotator_ui.py` — a Tkinter UI for reviewing/correcting the line segmentation and typing in the transcribed text per row.

An initial attempt to auto-label the dataset (Gemini for OCR + a valley-based row detector) produced unusable training data (CER > 1 after training). The dataset was therefore labeled with this semi-automatic, human-in-the-loop tool instead — **28 pages, 707 annotated lines** in total.

### 6. Model fine-tuning (`06-trocr_train.ipynb`)
Fine-tunes [`kazars24/trocr-base-handwritten-ru`](https://huggingface.co/kazars24/trocr-base-handwritten-ru) (a Cyrillic handwriting TrOCR checkpoint) on the annotated dataset:
- Extends the tokenizer vocabulary with pre-reform historical letters (`ѣ Ѣ і І ъ Ъ ѳ Ѳ ѕ Ѕ ы`) and resizes the decoder's embedding layer accordingly.
- Custom `Dataset`/`collate_fn` with dynamic padding (labels padded to -100 for loss masking) instead of static padding, for memory efficiency.
- Gradient accumulation (effective batch size = `batch_size × accum_steps`) to fit training on a single Colab T4 GPU.
- AdamW optimizer with a linear warmup/decay schedule.
- 90/10 train/validation split; validation uses beam search (`num_beams=4`) generation and Character Error Rate (CER) as the tracked metric; the best-CER checkpoint is saved separately from the final epoch checkpoint.

Training command:
```bash
python trocr_finetune.py --dataset /content/dataset --output /content/trocr_revizki \
    --batch-size 4 --accum-steps 4 --epochs 15
```

## Results

| Epoch | Train Loss | Val Loss | CER |
|------:|-----------:|---------:|-----:|
| 1  | 3.7489 | 2.5609 | 0.6514 |
| 3  | 1.2364 | 1.0525 | 0.4058 |
| 5  | 0.5238 | 0.8449 | 0.3555 |
| 7  | 0.2922 | 0.7997 | 0.2921 |
| 10 | 0.1154 | 0.8172 | 0.2789 |
| 12 | 0.0613 | 0.7800 | 0.2632 |
| 15 | 0.0299 | 0.7929 | **0.2500** |

Best model: **CER ≈ 0.25** on the held-out validation split, compared to **CER > 1** for the model trained on the initial auto-labeled (Gemini + valley-based) dataset — confirming that careful, semi-manual annotation was essential given the small dataset size and the difficulty of 18–19th century handwriting.

Training/validation loss and CER over 15 epochs:

*(see `Всі метрики (нормалізовано 0-1)` chart in the project write-up — train loss and CER both trend down steadily, with CER plateauing around epoch 10–15.)*

## Repository Structure

```
.
├── src/
│   ├── 01-split_pdf.py            # PDF → page PNGs
│   ├── 02-manual_split_web.py     # Flask tool: split page spreads into L/R
│   ├── 03-deskew.py               # Hough-based deskew
│   ├── 04-remove_header.py        # Tkinter tool: crop headers/margins
│   ├── 05-annotate/
│   │   ├── line_detector.py       # Row/line separator detection
│   │   ├── dataset_utils.py       # Line extraction, markup alignment, CSV/JSONL writers
│   │   └── dataset_annotator_ui.py# Tkinter annotation UI
│   └── 06-trocr_train.ipynb       # TrOCR fine-tuning + evaluation + inference demo
└── data/                          # step-00 (raw PDF) → step-05 (final dataset), gitignored/sample only
```

## Requirements

```
opencv-python
numpy
scipy
pillow
pdf2image        # requires poppler-utils installed on the system
flask
torch
torchvision
transformers
datasets
evaluate
jiwer
```

`pdf2image` requires the `poppler-utils` system package (`apt install poppler-utils` / `brew install poppler`).

## Usage

```bash
# 1. Split the source PDF into page images
python src/01-split_pdf.py

# 2. Split two-page spreads into left/right pages (open http://localhost:5000)
python src/02-manual_split_web.py --folder ./data/step-01/ --out ./data/step-02/

# 3. Deskew each page
python src/03-deskew.py input.jpg --out output_deskewed.jpg

# 4. Remove headers/margins (GUI)
python src/04-remove_header.py

# 5. Annotate line-level transcriptions (GUI)
python src/05-annotate/dataset_annotator_ui.py

# 6. Fine-tune TrOCR (see 06-trocr_train.ipynb, designed for Google Colab)
```

## Limitations & Next Steps

- Dataset is small (28 pages / 707 lines) and dominated by a single scribe's handwriting — the current CER of 0.25 reflects this.
- **Next steps to reach the target CER < 10%:**
  - Add more annotated pages, ideally spanning multiple handwriting styles/scribes.
  - Add data augmentation (rotation jitter, elastic distortion, contrast/brightness variation) to improve generalization from limited data.
  - Extend beyond line-level OCR to full NER (names, ages, roles, years) and automatic family-tree graph construction (`NetworkX`), as originally planned.

