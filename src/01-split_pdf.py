import os
from pdf2image import convert_from_path, pdfinfo_from_path

def split_large_pdf(pdf_path, output_folder="output", dpi=150):
    os.makedirs(output_folder, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    
    print("Reading PDF metadata...")
    # Get total page count without loading the whole file into RAM
    info = pdfinfo_from_path(pdf_path)
    total_pages = int(info["Pages"])
    print(f"Total pages found: {total_pages}. Starting conversion...")
    
    # Process 10 pages at a time to prevent RAM overload
    step = 10
    for start in range(1, total_pages + 1, step):
        end = min(start + step - 1, total_pages)
        print(f"Processing pages {start} to {end} of {total_pages}...")
        
        # Load only the specific range of pages into memory
        pages = convert_from_path(pdf_path, dpi=dpi, first_page=start, last_page=end)
        
        for i, page in enumerate(pages):
            current_page_num = start + i
            output_filename = f"{base_name}_page_{current_page_num:04d}.png"
            output_filepath = os.path.join(output_folder, output_filename)
            
            page.save(output_filepath, "PNG")
            
        # Free memory after each batch
        del pages

    print("Conversion completed successfully!")

if __name__ == "__main__":
    target_pdf = "source.pdf" 
    # Use dpi=150 for a great balance of speed and text readability.
    # Set to 200 or 300 for high-definition print quality (will run slower).
    split_large_pdf(target_pdf, dpi=150)
