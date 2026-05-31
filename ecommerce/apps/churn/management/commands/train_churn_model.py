import os

import joblib
import pandas as pd

from django.conf import settings
from django.core.management.base import BaseCommand

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split


class Command(BaseCommand):
    help = 'Train a Random Forest churn prediction model.'

    def handle(self, *args, **kwargs):
        dataset_path = os.path.join(
            settings.BASE_DIR,
            'datasets',
            'churn_dataset.csv'
        )

        if not os.path.exists(dataset_path):
            self.stdout.write(
                self.style.ERROR(
                    'Dataset not found. Run: python manage.py export_churn_dataset'
                )
            )
            return

        data = pd.read_csv(dataset_path)

        if data.empty:
            self.stdout.write(
                self.style.ERROR(
                    'Dataset is empty. Generate activity and run build_features again.'
                )
            )
            return

        if len(data) < 10:
            self.stdout.write(
                self.style.WARNING(
                    'Very small dataset. Model can be trained, but accuracy will not be reliable.'
                )
            )

        if data['churn_label'].nunique() < 2:
            self.stdout.write(
                self.style.ERROR(
                    'Training failed: dataset has only one class. You need both churned and non-churned users.'
                )
            )
            return

        X = data.drop(columns=['user_id', 'churn_label'])
        y = data['churn_label']

        test_size = 0.2

        if len(data) < 20:
            test_size = 0.3

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=test_size,
            random_state=42,
            stratify=y
        )

        model = RandomForestClassifier(
            n_estimators=100,
            random_state=42,
            class_weight='balanced'
        )

        model.fit(X_train, y_train)

        predictions = model.predict(X_test)

        accuracy = accuracy_score(y_test, predictions)

        self.stdout.write(
            self.style.SUCCESS(
                f'Model trained successfully. Accuracy: {accuracy:.2f}'
            )
        )

        self.stdout.write('\nClassification Report:')
        self.stdout.write(
            classification_report(y_test, predictions)
        )

        model_dir = os.path.join(settings.BASE_DIR, 'ml_models')
        os.makedirs(model_dir, exist_ok=True)

        model_path = os.path.join(model_dir, 'churn_model.pkl')

        joblib.dump(model, model_path)

        self.stdout.write(
            self.style.SUCCESS(
                f'Model saved successfully at: {model_path}'
            )
        )