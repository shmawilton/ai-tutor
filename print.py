import os
import numpy as np
import matplotlib.pyplot as plt

# Set output folder for plots
output_folder = "plots"
if not os.path.exists(output_folder):
    os.makedirs(output_folder)
    print(f"Created output folder: {output_folder}")
else:
    print(f"Output folder already exists: {output_folder}")

# Define directories and splits
DEST_DIR = "posture_data"
splits = ['train', 'val', 'test']
classes = ['correct_posture', 'incorrect_posture']

# Dictionary to store counts
counts = {}

# Loop through each split and each class to count images
for split in splits:
    counts[split] = {}
    for cls in classes:
        folder_path = os.path.join(DEST_DIR, split, cls)
        if os.path.exists(folder_path):
            files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.png'))]
            counts[split][cls] = len(files)
        else:
            counts[split][cls] = 0

# Print out counts for verification
print("Image counts per split and class:")
for split in splits:
    print(f"{split}: {counts[split]}")

# ---------------------------
# Overall Distribution Pie Chart
# ---------------------------
total_correct = sum(counts[split]['correct_posture'] for split in splits)
total_incorrect = sum(counts[split]['incorrect_posture'] for split in splits)
total_counts = [total_correct, total_incorrect]
labels = ['Correct Posture', 'Incorrect Posture']

plt.figure(figsize=(6,6))
plt.pie(total_counts, labels=labels, autopct='%1.1f%%', startangle=90, colors=['#66b3ff','#ff9999'])
plt.title("Overall Distribution of Posture Images")
overall_pie_path = os.path.join(output_folder, "overall_distribution_pie.png")
plt.savefig(overall_pie_path, dpi=300)
print(f"Saved overall distribution pie chart to: {overall_pie_path}")
plt.show()

# ---------------------------
# Grouped Bar Chart for Train/Val/Test Splits
# ---------------------------
x = np.arange(len(splits))  # the label locations
width = 0.35  # width of the bars

correct_counts = [counts[split]['correct_posture'] for split in splits]
incorrect_counts = [counts[split]['incorrect_posture'] for split in splits]

fig, ax = plt.subplots(figsize=(8,6))
rects1 = ax.bar(x - width/2, correct_counts, width, label='Correct Posture', color='#66b3ff')
rects2 = ax.bar(x + width/2, incorrect_counts, width, label='Incorrect Posture', color='#ff9999')

ax.set_ylabel('Number of Images')
ax.set_title('Image Counts by Data Split and Posture Type')
ax.set_xticks(x)
ax.set_xticklabels(splits)
ax.legend()

# Attach text labels on top of the bars
def autolabel(rects):
    for rect in rects:
        height = rect.get_height()
        ax.annotate(f'{height}',
                    xy=(rect.get_x() + rect.get_width()/2, height),
                    xytext=(0,3), textcoords="offset points",
                    ha='center', va='bottom')

autolabel(rects1)
autolabel(rects2)

fig.tight_layout()
bar_chart_path = os.path.join(output_folder, "split_distribution_bar.png")
plt.savefig(bar_chart_path, dpi=300)
print(f"Saved split distribution bar chart to: {bar_chart_path}")
plt.show()
