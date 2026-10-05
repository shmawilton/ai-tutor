import os
import csv
import torch
import torch.nn as nn
import torch.optim as optim
import matplotlib.pyplot as plt
from torchvision import datasets, models, transforms
from torch.utils.data import DataLoader
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
import numpy as np

def train_model(model, criterion, optimizer, num_epochs=10):
    """
    Trains the model, logs metrics to a CSV, and returns the best model.
    """
    # Lists to store metrics each epoch
    history = {
        'epoch': [],
        'train_loss': [],
        'train_acc': [],
        'val_loss': [],
        'val_acc': [],
    }

    best_acc = 0.0

    # Open CSV and write header
    with open('training_log.csv', mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['epoch', 'train_loss', 'train_acc', 'val_loss', 'val_acc', 'best_val_acc_so_far'])

        for epoch in range(num_epochs):
            print(f"Epoch {epoch+1}/{num_epochs}")
            epoch_data = {
                'train_loss': 0.0,
                'train_corrects': 0,
                'val_loss': 0.0,
                'val_corrects': 0
            }

            for phase in ['train', 'val']:
                if phase == 'train':
                    model.train()
                else:
                    model.eval()

                running_loss = 0.0
                running_corrects = 0

                for inputs, labels in dataloaders[phase]:
                    inputs = inputs.to(device)
                    labels = labels.to(device)

                    optimizer.zero_grad()

                    with torch.set_grad_enabled(phase == 'train'):
                        outputs = model(inputs)
                        _, preds = torch.max(outputs, 1)
                        loss = criterion(outputs, labels)

                        if phase == 'train':
                            loss.backward()
                            optimizer.step()

                    running_loss += loss.item() * inputs.size(0)
                    running_corrects += torch.sum(preds == labels.data)

                epoch_loss = running_loss / len(image_datasets[phase])
                epoch_acc = running_corrects.double() / len(image_datasets[phase])

                print(f"{phase} Loss: {epoch_loss:.4f} Acc: {epoch_acc:.4f}")

                # Record metrics
                if phase == 'train':
                    epoch_data['train_loss'] = epoch_loss
                    epoch_data['train_corrects'] = epoch_acc.item()
                else:
                    epoch_data['val_loss'] = epoch_loss
                    epoch_data['val_corrects'] = epoch_acc.item()

                # Save best model if on val phase
                if phase == 'val' and epoch_acc > best_acc:
                    best_acc = epoch_acc
                    torch.save(model.state_dict(), "best_posture_model.pth")
                    print("Model saved with val acc =", best_acc.item())

            # End of epoch, log metrics for CSV
            history['epoch'].append(epoch+1)
            history['train_loss'].append(epoch_data['train_loss'])
            history['train_acc'].append(epoch_data['train_corrects'])
            history['val_loss'].append(epoch_data['val_loss'])
            history['val_acc'].append(epoch_data['val_corrects'])

            with open('training_log.csv', mode='a', newline='') as f2:
                writer2 = csv.writer(f2)
                writer2.writerow([
                    epoch+1,
                    epoch_data['train_loss'],
                    epoch_data['train_corrects'],
                    epoch_data['val_loss'],
                    epoch_data['val_corrects'],
                    best_acc.item()
                ])

    # After training, return the history dict and the best model
    return model, history

if __name__ == "__main__":
    # 1. Setup
    data_dir = "posture_data"
    batch_size = 8
    num_epochs = 50

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 2. Data Transforms
    data_transforms = {
        'train': transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406],
                                 [0.229, 0.224, 0.225])
        ]),
        'val': transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406],
                                 [0.229, 0.224, 0.225])
        ])
    }

    # 3. Datasets and Dataloaders
    image_datasets = {
        x: datasets.ImageFolder(os.path.join(data_dir, x),
                                data_transforms[x if x != 'test' else 'val'])
        for x in ['train', 'val', 'test']
    }

    dataloaders = {
        x: DataLoader(image_datasets[x],
                      batch_size=batch_size,
                      shuffle=True,
                      num_workers=2)
        for x in ['train', 'val', 'test']
    }

    class_names = image_datasets['train'].classes  # ['correct_posture', 'incorrect_posture']

    # 4. Load a Pre-trained Model (ResNet18)
    model = models.resnet18(pretrained=True)
    num_ftrs = model.fc.in_features
    model.fc = nn.Linear(num_ftrs, 2)
    model = model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=0.001, momentum=0.9)

    # 5. Run Training
    model, history = train_model(model, criterion, optimizer, num_epochs)
    print("Training complete.")

    # ======================
    #      PLOT 1 & 2
    # ======================
    # Plot Train vs Val Loss
    plt.figure(figsize=(10, 4))
    plt.plot(history['epoch'], history['train_loss'], label='Train Loss')
    plt.plot(history['epoch'], history['val_loss'], label='Val Loss')
    plt.title('Train vs Val Loss')
    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.legend()
    plt.savefig('loss_plot.png', dpi=300)
    plt.show()

    # Plot Train vs Val Accuracy
    plt.figure(figsize=(10, 4))
    plt.plot(history['epoch'], history['train_acc'], label='Train Acc')
    plt.plot(history['epoch'], history['val_acc'], label='Val Acc')
    plt.title('Train vs Val Accuracy')
    plt.xlabel('Epoch')
    plt.ylabel('Accuracy')
    plt.legend()
    plt.savefig('accuracy_plot.png', dpi=300)
    plt.show()

    # 6. TEST EVALUATION
    model.load_state_dict(torch.load("best_posture_model.pth"))
    model.eval()

    # ======================
    #      PLOT 3
    #   Confusion Matrix
    # ======================
    # Collect all predictions/labels for the test set
    y_true = []
    y_pred = []

    for inputs, labels in dataloaders['test']:
        inputs = inputs.to(device)
        labels = labels.to(device)
        with torch.no_grad():
            outputs = model(inputs)
            _, preds = torch.max(outputs, 1)

        y_true.extend(labels.cpu().numpy())
        y_pred.extend(preds.cpu().numpy())

    # Build confusion matrix
    cm = confusion_matrix(y_true, y_pred)
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=class_names)

    # Plot and save confusion matrix
    disp.plot(cmap=plt.cm.Blues)
    plt.title("Confusion Matrix (Test Set)")
    plt.savefig('confusion_matrix.png', dpi=300)
    plt.show()

    # Compute final test accuracy
    test_acc_count = sum(1 for i in range(len(y_true)) if y_true[i] == y_pred[i])
    test_acc = test_acc_count / len(y_true)
    print(f"Test accuracy: {test_acc:.4f}")
