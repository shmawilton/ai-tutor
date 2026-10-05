import csv
import matplotlib.pyplot as plt
import numpy as np

# Read the training log
epochs = []
train_loss = []
train_acc = []
val_loss = []
val_acc = []
best_val_acc = []

def safe_float(value):
    """Convert string to float, return 0.0 if empty or invalid."""
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return 0.0

with open('training_log.csv', 'r') as f:
    reader = csv.reader(f)
    next(reader)  # Skip header row
    for row in reader:
        # Clean up the data and convert to float
        clean_row = [x.strip() for x in row]
        if len(clean_row) >= 6:  # Only process rows with enough columns
            epochs.append(safe_float(clean_row[0]))
            train_loss.append(safe_float(clean_row[1]))
            train_acc.append(safe_float(clean_row[2]))
            val_loss.append(safe_float(clean_row[3]))
            val_acc.append(safe_float(clean_row[4]))
            best_val_acc.append(safe_float(clean_row[5]))

# Convert to numpy arrays for easier manipulation
epochs = np.array(epochs)
train_loss = np.array(train_loss)
train_acc = np.array(train_acc)
val_loss = np.array(val_loss)
val_acc = np.array(val_acc)
best_val_acc = np.array(best_val_acc)

# Set the style for better visualization
plt.style.use('bmh')

# Create a figure with multiple subplots
fig = plt.figure(figsize=(15, 10))
gs = fig.add_gridspec(2, 2)

# 1. Training and Validation Loss
ax1 = fig.add_subplot(gs[0, 0])
ax1.plot(epochs, train_loss, label='Training Loss', linewidth=2)
ax1.plot(epochs, val_loss, label='Validation Loss', linewidth=2)
ax1.set_title('Training and Validation Loss Over Time')
ax1.set_xlabel('Epoch')
ax1.set_ylabel('Loss')
ax1.grid(True)
ax1.legend()

# 2. Training and Validation Accuracy
ax2 = fig.add_subplot(gs[0, 1])
ax2.plot(epochs, train_acc, label='Training Accuracy', linewidth=2)
ax2.plot(epochs, val_acc, label='Validation Accuracy', linewidth=2)
ax2.plot(epochs, best_val_acc, label='Best Validation Accuracy', 
         linestyle='--', alpha=0.7, linewidth=2)
ax2.set_title('Training and Validation Accuracy Over Time')
ax2.set_xlabel('Epoch')
ax2.set_ylabel('Accuracy')
ax2.grid(True)
ax2.legend()

# 3. Loss vs Accuracy (Training)
ax3 = fig.add_subplot(gs[1, 0])
scatter = ax3.scatter(train_loss, train_acc, c=epochs, cmap='viridis')
ax3.set_title('Training Loss vs Accuracy')
ax3.set_xlabel('Training Loss')
ax3.set_ylabel('Training Accuracy')
ax3.grid(True)

# Add colorbar for epoch progression
plt.colorbar(scatter, ax=ax3, label='Epoch')

# 4. Validation Loss vs Accuracy
ax4 = fig.add_subplot(gs[1, 1])
scatter = ax4.scatter(val_loss, val_acc, c=epochs, cmap='viridis')
ax4.set_title('Validation Loss vs Accuracy')
ax4.set_xlabel('Validation Loss')
ax4.set_ylabel('Validation Accuracy')
ax4.grid(True)

# Add colorbar for epoch progression
plt.colorbar(scatter, ax=ax4, label='Epoch')

# Adjust layout and save
plt.tight_layout()
plt.savefig('training_analysis.png', dpi=300, bbox_inches='tight')

# Print some statistics
print("\nTraining Statistics:")
print("-" * 50)
print(f"Best Validation Accuracy: {np.max(best_val_acc):.4f}")
print(f"Final Training Accuracy: {train_acc[-1]:.4f}")
print(f"Final Validation Accuracy: {val_acc[-1]:.4f}")
print(f"Final Training Loss: {train_loss[-1]:.4f}")
print(f"Final Validation Loss: {val_loss[-1]:.4f}")

# Calculate improvement metrics
initial_val_acc = val_acc[0]
final_val_acc = val_acc[-1]
improvement = ((final_val_acc - initial_val_acc) / initial_val_acc) * 100

print("\nImprovement Metrics:")
print("-" * 50)
print(f"Validation Accuracy Improvement: {improvement:.2f}%")
print(f"Epochs to Best Accuracy: {epochs[np.argmax(best_val_acc)]}") 