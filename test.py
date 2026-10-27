import json
import timeit

import pandas as pd
import rectpack
import rectpack.guillotine as guillotine
from rectpack import PackingMode, newPacker

# ---------------------------------------------------------
# Step 1: Convert XLSX to CSV
# ---------------------------------------------------------
excel_file = "Automne de l'IA 2026 SG DDM - Données articles et matières.xlsx"
csv_file = "Données_articles_et_matières.csv"

# Choose your target sheet: use the exact sheet name (string) or index (integer, e.g., 1 for the second sheet)
target_sheet = "Articles"

# Load Excel and export to CSV
df_excel = pd.read_excel(excel_file, sheet_name=target_sheet, engine="openpyxl")
df_excel.to_csv(csv_file, index=False)
print(f"Successfully converted {excel_file} to {csv_file}")

# ---------------------------------------------------------
# Step 2: Extract desired columns from the converted CSV
# ---------------------------------------------------------
df = pd.read_csv(csv_file)
# Focus on a specific coloris (e.g., 215371, 220965) for this example. Adjust as needed.
filtered_df = df[df["Coloris"] == 215371]

# Expected CSV columns : 'Article', 'Désignation article', 'X', 'Y', 'quantity'
components = []
for _, row in filtered_df.iterrows():
    article_id = str(row["Article"])
    Designation_article = str(row["Désignation article"])
    article_x = int(row["X"])  # type: ignore
    article_y = int(row["Y"])  # type: ignore
    quantity = int(row["QtéParSemaine"])  # type: ignore

    # Expand quantities into individual component items
    for q in range(quantity):
        components.append((f"{Designation_article}_{q}", article_x, article_y))

print(f"Extracted {len(components)} total individual panels to cut in a week.")

# ---------------------------------------------------------
# Step 3: Run rectpack Optimization
# ---------------------------------------------------------
# Standard wood panel dimensions (e.g., 2440mm x 1220mm)
panel_x = 26550
panel_y = 21000

# Check for oversized components before packing
oversized = [
    comp
    for comp in components
    if (comp[1] > panel_x or comp[2] > panel_y)
    and (comp[1] > panel_x or comp[2] > panel_y)
]

if oversized:
    print(
        f"⚠️ Found {len(oversized)} components larger than the sheet size ({panel_x}x{panel_y}):"
    )
    for comp in oversized[:5]:  # Print first 5 examples
        print(f"   - {comp[0]}: {comp[1]} x {comp[2]}")
else:
    print("✅ All individual components fit within sheet dimensions.")

# Estimate required sheets based on total area + a 30% buffer for waste
total_component_area = sum(w * h for _, w, h in components)
panel_area = panel_x * panel_y
estimated_sheets_needed = int((total_component_area / panel_area) * 1.3) + 10

print(f"Allocating {estimated_sheets_needed} wood sheets for optimization...")


# Initialize the packer
# Using Guillotine mode ensures cuts go edge-to-edge (suitable for panel saws)
packer = newPacker(
    mode=PackingMode.Offline,
    # Best Short Side Fit heuristic
    pack_algo=guillotine.GuillotineBssfSas,  # type: ignore
    rotation=True,  # Allow rotation if grain direction permits
)

# Add large stock bins (wood sheets). Add enough sheets to fit all components.
for i in range(estimated_sheets_needed):
    packer.add_bin(panel_x, panel_y, bin_id=i)

# Add components to the packer
for cid, article_x, article_y in components:
    packer.add_rect(article_x, article_y, rid=cid)

# Execute the optimization
start_time=timeit.default_timer()
packer.pack()  # type: ignore
print(f"Executing Time: {timeit.default_timer()-start_time}")

# ---------------------------------------------------------
# Step 4: Analyze Results & Calculate Waste Rate (Taux de Chute)
# ---------------------------------------------------------
packed_rids = set(rect[5] for rect in packer.rect_list())

# Find which components didn't make it into the bins
unpacked_components = [comp for comp in components if comp[0] not in packed_rids]

if unpacked_components:
    print(
        f"⚠️ WARNING: {len(unpacked_components)} components could NOT fit on the sheets!"
    )
    for comp in unpacked_components:
        print(f"   - Unpacked item: ID={comp[0]}, Width={comp[1]}, Height={comp[2]}")
else:
    print("✅ Success: All components were successfully packed.")

all_rects = packer.rect_list()

if not all_rects:
    print(
        "Error: No components could be packed. Check if individual parts exceed sheet dimensions."
    )
else:
    # Identify unique sheets used
    used_bins = set(rect[0] for rect in all_rects)
    num_used_sheets = len(used_bins)

    # Calculate areas
    sheet_area = panel_x * panel_y
    total_board_area = num_used_sheets * sheet_area

    placed_rects_area = sum(rect[3] * rect[4] for rect in all_rects)

    waste_area = total_board_area - placed_rects_area
    waste_rate = (waste_area / total_board_area) * 100

    print("\n--- Optimization Results ---")
    print(f"Total Wood Sheets Used: {num_used_sheets}")
    print(f"Total Component Area:   {placed_rects_area / 1e6:.2f} m²")
    print(f"Total Stock Area:       {total_board_area / 1e6:.2f} m²")
    print(f"Taux de Chute (Waste):  {waste_rate:.2f}%")

# ---------------------------------------------------------
# Step 5: Export Layout to JSON
# ---------------------------------------------------------
# Organize packed rectangles by sheet (bin_id)
layout_data = {}

for rect in packer.rect_list():
    bin_id = int(rect[0])
    x = int(rect[1])
    y = int(rect[2])
    width = int(rect[3])
    height = int(rect[4])
    item_id = str(rect[5])

    sheet_key = f"sheet_{bin_id}"
    if sheet_key not in layout_data:
        layout_data[sheet_key] = []

    layout_data[sheet_key].append(
        {"id": item_id, "x": x, "y": y, "width": width, "height": height}
    )

# Save to a JSON file
json_output_path = "cutting_layout.json"
with open(json_output_path, "w", encoding="utf-8") as f:
    json.dump(layout_data, f, indent=4)

print(f"Cutting layout successfully saved to {json_output_path}")
