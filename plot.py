import json
import glob
import matplotlib.pyplot as plt

Algorithms_Types = ["Guillotine", "MaxRects", "Skyline"]

def plot_cutting_analysis(algo_index=0, file_pattern=None):
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
    plt.title('Comparison de Temps d\'Éxecution par Algorithme')
    plt.xticks(rotation=45, ha='right')
    plt.legend()

    # Chart 2: Waste Rate
    plt.subplot(1, 2, 2)
    plt.bar(algorithms, waste_rates, width=0.5, color='salmon', edgecolor='black')
    mean_waste_rate = sum(waste_rates) / len(waste_rates) if waste_rates else 0
    plt.axhline(y=mean_waste_rate, color='red', linestyle='--', linewidth=1.5, label=f'Mean: {mean_waste_rate:.2f}%')
    plt.xlabel(current_algo_type)
    plt.ylabel('Taux de Chute (%)')
    plt.title('TdC par Algorithme')
    plt.xticks(rotation=45, ha='right')
    plt.legend()

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    plot_cutting_analysis(algo_index=1)