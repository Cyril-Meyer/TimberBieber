import json
import timeit

import numpy as np
import pandas as pd
import rectpack.guillotine as guillotine
import rectpack.maxrects as maxrects
import rectpack.skyline as skyline
from rectpack import PackingBin, PackingMode, newPacker

excel_files = [
    "Automne de l'IA 2026 SG DDM - Données articles et matières.xlsx",
    "Automne de l'IA 2026 SG DDM - OFs et TdC.xlsx",
]
csv_list = ["Données_articles.csv", "Données_matières.csv", "Données_OF.csv"]


def load_base_data():
    """Loads raw Excel files into CSV and returns base dataframes and panel dimensions."""
    pd.read_excel(excel_files[0], sheet_name="Articles").to_csv(csv_list[0], index=False)
    pd.read_excel(excel_files[0], sheet_name="Matière").to_csv(csv_list[1], index=False)
    pd.read_excel(excel_files[1], sheet_name="OF").to_csv(csv_list[2], index=False)

    df_matiere = pd.read_csv(csv_list[1])
    panel_x = int(df_matiere[df_matiere["Matiere"] == 215371]["X"].values[0])  # type: ignore
    panel_y = int(df_matiere[df_matiere["Matiere"] == 215371]["Y"].values[0])  # type: ignore

    df_OF = pd.read_csv(csv_list[2])
    df_article = pd.read_csv(csv_list[0])

    return panel_x, panel_y, df_OF, df_article


def get_weekly_components(df_OF, df_article):
    """Filters OF data and groups components by ISO calendar weeks (S17 to S42)."""
    df_OF["DateProd"] = pd.to_datetime(df_OF["DateProd"], errors="coerce")

    # Extract ISO Year and Week
    iso_cal = df_OF["DateProd"].dt.isocalendar()
    df_OF["ISO_Year"] = iso_cal["year"]
    df_OF["ISO_Week"] = iso_cal["week"]

    # Filter for weeks 17 to 42 in the year 2026
    df_filtered_of = df_OF[
        (df_OF["ISO_Year"] == 2026) & 
        (df_OF["ISO_Week"] >= 17) & 
        (df_OF["ISO_Week"] <= 42)
    ].copy()

    weekly_data = {}

    # Group by ISO week
    for (year, week), group in df_filtered_of.groupby(["ISO_Year", "ISO_Week"]):
        week_label = f"{year}/S{week:02d}" # e.g., "2026/S17"

        # Aggregate demand per article for this ISO week
        df_aggregated = group.groupby("Article", as_index=False)["Qté cdée"].sum()

        # Merge with article specs for coloris 215371
        df_merged = df_aggregated.merge(
            df_article[df_article["Coloris"] == 215371], on="Article"
        )

        if df_merged.empty:
            continue

        # Apply batch rounding (QtéParOF rules)
        multiple = df_merged["QtéParOF"].fillna(1).clip(lower=1)
        df_merged["Qte_final"] = (
            np.ceil(df_merged["Qté cdée"] / multiple) * multiple
        ).astype(int)

        # Expand into individual components list for this week
        components = []
        for _, row in df_merged.iterrows():
            designation = str(row["Désignation article"])
            x = int(row["X"])  # type: ignore
            y = int(row["Y"])  # type: ignore
            qty = int(row["Qte_final"])  # type: ignore

            for q in range(qty):
                components.append((f"{designation}_{q}", x, y))

        weekly_data[week_label] = {
            "total_command": int(group["Qté cdée"].sum()),
            "components": components,
        }

    return weekly_data


def run_optimization_for_week(semaine_str, components, algo_type, algo, panel_x, panel_y):
    """Executes packing optimization for a specific week and algorithm, then saves to JSON."""
    print(f"[{semaine_str}] Running {algo_type} -> {algo.__name__} ({len(components)} panels to cut)")
    
    packer = newPacker(
        mode=PackingMode.Offline,
        bin_algo=PackingBin.BBF,
        pack_algo=algo,  # type: ignore
        rotation=False,
    )

    packer.add_bin(panel_x, panel_y, count=float("inf"))  # type: ignore

    for cid, article_x, article_y in components:
        packer.add_rect(article_x, article_y, rid=cid)

    start_time = timeit.default_timer()
    packer.pack()  # type: ignore
    executed_time = timeit.default_timer() - start_time

    all_rects = packer.rect_list()
    if not all_rects:
        print(f"[{semaine_str}] Error: No components could be packed.")
        return

    num_used_sheets = len(packer)
    surface_utilisee = sum(b.used_area() for b in packer)
    total_board_area = num_used_sheets * panel_x * panel_y
    waste_rate = (1.0 - (surface_utilisee / total_board_area)) * 100

    layout_data = {
        "week": semaine_str,
        "algorithm": {
            "type": algo_type,
            "name": algo.__name__,
            "waste_rate (%)": waste_rate,
            "execution_time (seconds)": executed_time,
            "total_wood_sheets_used": num_used_sheets,
        }
    }

    sheets_data = {}
    for rect in packer.rect_list():
        bin_id, x, y, width, height, item_id = int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]), int(rect[4]), str(rect[5])
        sheet_key = f"sheet_{bin_id}"
        
        if sheet_key not in sheets_data:
            sheets_data[sheet_key] = []

        sheets_data[sheet_key].append({
            "article": item_id,
            "position_x": x,
            "position_y": y,
            "article_x": width,
            "article_y": height,
        })

    sheet_area = panel_x * panel_y
    for sheet_key, items in sheets_data.items():
        used_area = sum(item["article_x"] * item["article_y"] for item in items)
        sheet_waste_area = sheet_area - used_area
        sheet_waste_rate = (sheet_waste_area / sheet_area) * 100

        layout_data[sheet_key] = {
            "sheet_dimensions": {"width": panel_x, "height": panel_y},
            "used_area": used_area,
            "waste_area": sheet_waste_area,
            "waste_rate_percent": sheet_waste_rate,
            "placed_items": items,
        }

    safe_week_str = semaine_str.replace("/", "-")
    json_output_path = f"layout_{safe_week_str}_{algo_type}_{algo.__name__}.json"
    with open(json_output_path, "w", encoding="utf-8") as f:
        json.dump(layout_data, f, indent=4)


if __name__ == "__main__":
    panel_x, panel_y, df_OF, df_article = load_base_data()
    weekly_data = get_weekly_components(df_OF, df_article)

    algorithms = {
        "MaxRects": [
            maxrects.MaxRectsBl,
            maxrects.MaxRectsBssf,
            maxrects.MaxRectsBaf,
            maxrects.MaxRectsBlsf,
        ],
        "Skyline": [
            skyline.SkylineBl,
            skyline.SkylineBlWm,
            skyline.SkylineMwf,
            skyline.SkylineMwfl,
            skyline.SkylineMwfWm,
            skyline.SkylineMwflWm,
        ],
        "Guillotine": [
            guillotine.GuillotineBssfSas,
            guillotine.GuillotineBssfLas,
            guillotine.GuillotineBssfSlas,
            guillotine.GuillotineBssfLlas,
            guillotine.GuillotineBssfMaxas,
            guillotine.GuillotineBssfMinas,
            guillotine.GuillotineBlsfSas,
            guillotine.GuillotineBlsfLas,
            guillotine.GuillotineBlsfSlas,
            guillotine.GuillotineBlsfLlas,
            guillotine.GuillotineBlsfMaxas,
            guillotine.GuillotineBlsfMinas,
            guillotine.GuillotineBafSas,
            guillotine.GuillotineBafLas,
            guillotine.GuillotineBafSlas,
            guillotine.GuillotineBafLlas,
            guillotine.GuillotineBafMaxas,
            guillotine.GuillotineBafMinas,
        ],
    }

    for algo_type, algo_list in algorithms.items():
        for algo in algo_list:
            run_optimization_for_week(
                "2026/S17", weekly_data["2026/S17"]["components"], algo_type, algo, panel_x, panel_y
            )
    """
    # Loop through each week and each algorithm
    for semaine, data in weekly_data.items():
        print(f"\n--- Processing Week starting: {semaine} (Total Ordered Qty: {data['total_command']}) ---")
        
        for algo_type, algo_list in algorithms.items():
            for algo in algo_list:
                run_optimization_for_week(
                    semaine, data["components"], algo_type, algo, panel_x, panel_y
                )
    """