import json
import glob
import matplotlib.pyplot as plt

Algorithms_Types = ["Guillotine", "MaxRects", "Skyline"]
# 5 best algos for each type of algorithme for comparasion
Algo_Choisi = ["GuillotineBssfLas", "GuillotineBssfLlas", "GuillotineBssfMaxas", "MaxRectsBssf", "MaxRectsBlsf"]

def global_analysis(algo_index=0, file_pattern=None, algo_bin = None, algo_sort = None):
    """
    Extracts data from cutting layout JSON files, sorts them from best to worst 
    (lowest waste rate to highest), and plots execution time and waste rate.
    """
    if file_pattern is None:
        current_algo_type = Algorithms_Types[algo_index]
        file_pattern = f"layout_*_{current_algo_type}_*.json" 

    json_files = glob.glob(file_pattern)
    print(f"DEBUG: Found {len(json_files)} files matching pattern: {file_pattern}")

    if not json_files:
        print("No cutting layout JSON files found.")
        return

    algorithms = []
    execution_times = []
    waste_rates = []

    for file_path in json_files:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # Read metadata stored in the "algorithm" key
        algo_info = data.get("algorithm", {})
        algo_name = algo_info.get("name", file_path)
        exec_time = float(algo_info.get("execution_time (seconds)", 0))
        waste = float(algo_info.get("waste_rate (%)", 0))
        
        algorithms.append(algo_name)
        execution_times.append(exec_time)
        waste_rates.append(waste)

    if not execution_times or all(v == 0 for v in execution_times):
        print("WARNING: All execution times are 0 or lists are empty! Check your JSON structure.")
        return

    
    combined = list(zip(algorithms, execution_times, waste_rates))
    combined.sort(key=lambda x: x[2])  # Sorts ascending by waste_rates
    
    if combined:
        algorithms, execution_times, waste_rates = zip(*combined)
        algorithms = list(algorithms)
        execution_times = list(execution_times)
        waste_rates = list(waste_rates)

    # 3. Create the Matplotlib plots
    plt.figure(figsize=(12, 5))
    current_algo_type = Algorithms_Types[algo_index]

    # Chart 1: Execution Time
    plt.subplot(1, 2, 1)
    plt.bar(algorithms, execution_times, width=0.5, color='skyblue', edgecolor='black')
    mean_time = sum(execution_times) / len(execution_times) if execution_times else 0
    plt.axhline(y=mean_time, color='red', linestyle='--', linewidth=1.5, label=f'Mean: {mean_time:.2f}s')
    plt.xlabel(current_algo_type)
    plt.ylabel('Temps d\'Éxecution (seconds)')
    plt.title(f'Comparison de Temps d\'Éxecution (bin_algo = {algo_bin})')
    plt.xticks(rotation=45, ha='right')
    plt.legend()

    # Chart 2: Waste Rate
    plt.subplot(1, 2, 2)
    plt.bar(algorithms, waste_rates, width=0.5, color='salmon', edgecolor='black')
    mean_waste_rate = sum(waste_rates) / len(waste_rates) if waste_rates else 0
    plt.axhline(y=mean_waste_rate, color='red', linestyle='--', linewidth=1.5, label=f'Mean: {mean_waste_rate:.2f}%')
    plt.xlabel(current_algo_type)
    plt.ylabel('Taux de Chute (%)')
    plt.title(f'TdC (bin_algo = {algo_bin})')
    plt.xticks(rotation=45, ha='right')
    plt.legend()

    plt.tight_layout()
    plt.savefig(f'Figure_{algo_bin}_{algo_sort}_{current_algo_type}.png', dpi=300)
    plt.show()

def plot_weekly_cutting_analysis(algo_index=0, algo = None):
    """
    Extracts weekly cutting layout data from JSON files and plots 
    a combined dual-axis chart with fixed padding to avoid text overlaps.
    """
    current_algo_type = Algorithms_Types[algo_index]
    file_pattern = f"layout_*_{current_algo_type}_{algo}.json"
    json_files = glob.glob(file_pattern)
    print(f"DEBUG: Found {len(json_files)} files matching pattern: {file_pattern}")

    if not json_files:
        print("No cutting layout JSON files found.")
        return

    weeks = []
    panels_to_cut = []
    waste_rates = []

    # Sort files to ensure chronological week order
    for file_path in sorted(json_files):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        week_str = data.get("week", "Unknown")
        algo_info = data.get("algorithm", {})
        waste = float(algo_info.get("waste_rate (%)", 0))
        
        # Count total placed items (panels to cut) across all sheets in this week's JSON
        total_items = 0
        for key, val in data.items():
            if key.startswith("sheet_"):
                total_items += len(val.get("placed_items", []))
        
        weeks.append(week_str)
        panels_to_cut.append(total_items)
        waste_rates.append(waste)

    if not weeks:
        print("WARNING: No valid week data extracted!")
        return

    # Create the Combined Dual-Axis Figure
    fig, ax1 = plt.subplots(figsize=(14, 6))

    # --- Left Axis: Panels to Cut (Bar Chart) ---
    color_bars = '#93c5fd'
    ax1.set_xlabel('Semaine', fontweight='bold')
    ax1.set_ylabel('Nombre de Pièces à Couper', color='#1e3a8a', fontweight='bold')
    bars = ax1.bar(weeks, panels_to_cut, width=0.4, color=color_bars, edgecolor='#1e3a8a', alpha=0.8, label='Pièces à couper')
    ax1.tick_params(axis='y', labelcolor='#1e3a8a')
    ax1.grid(axis='y', alpha=0.3)
    
    # Give the left axis extra headroom for bar labels/bars
    ax1.set_ylim(0, max(panels_to_cut) * 1.15)

    # --- Right Axis: Waste Rate (Dot-Line Chart) ---
    ax2 = ax1.twinx()  
    color_line = '#2563eb'
    ax2.set_ylabel('Taux de Chute (%)', color=color_line, fontweight='bold')
    line = ax2.plot(weeks, waste_rates, marker="o", linewidth=2.5, color=color_line, label="TDC (%)")
    
    # Annotate each waste data point with its percentage value
    for x, y in zip(weeks, waste_rates):
        ax2.annotate(f"{y:.1f}%", (x, y), textcoords="offset points",
                     xytext=(0, 10), ha="center", fontsize=9, color=color_line, fontweight='bold')
        
    ax2.tick_params(axis='y', labelcolor=color_line)
    ax2.grid(False)  

    # Add mean reference lines for clarity
    mean_waste = sum(waste_rates) / len(waste_rates) if waste_rates else 0
    ax2.axhline(y=mean_waste, color='red', linestyle='--', linewidth=1.5, alpha=0.7, label=f'Mean TDC: {mean_waste:.2f}%')

    """
    # Add headroom to the right axis so annotations at the top never get cut off
    y_min, y_max = min(waste_rates), max(waste_rates)
    ax2.set_ylim(y_min - 0.5, y_max + 2.0)
    """
    ax2.set_ylim(0, 22) # Fixed upper limit to avoid cutting off annotations
    

    # Formatting and Layout
    plt.title(f'Volume de Commande vs. Taux de Chute (TdC) par Semaine ({algo})', fontsize=12, fontweight='bold', pad=15)
    ax1.set_xticks(range(len(weeks)))
    ax1.set_xticklabels(weeks, rotation=45, ha='right')

    # FIX: Moved legend to 'upper right' to avoid the dense data points on the left
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper right')

    plt.tight_layout()
    plt.savefig(f'Figure_Analyse_par_Semaine_{algo}.png', dpi=300)
    plt.show()

if __name__ == "__main__":
    global_analysis(algo_index=2,algo_bin="Global") 
    # for i in range(2):
        # global_analysis(algo_index=i,algo_bin="BBF",algo_sort="SORT_RATIO")  
    # plot_weekly_cutting_analysis(algo_index=0, algo="GuillotineBssfMaxas")