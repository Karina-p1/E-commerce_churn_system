import os

import joblib
import pandas as pd

from django.conf import settings
from django.core.management.base import BaseCommand

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    classification_report,
)

from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.svm import SVC

from xgboost import XGBClassifier


class Command(BaseCommand):
    help = 'Compare multiple ML models for churn prediction.'

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
                    'Dataset is empty. Add feature data first.'
                )
            )
            return

        if 'churn_label' not in data.columns:
            self.stdout.write(
                self.style.ERROR(
                    'churn_label column is missing from the dataset.'
                )
            )
            return

        if data['churn_label'].nunique() < 2:
            self.stdout.write(
                self.style.ERROR(
                    'Dataset must contain both churned and non-churned users.'
                )
            )
            return

        X = data.drop(
            columns=['user_id', 'User', 'churn_label'],
            errors='ignore'
        )

        y = data['churn_label']

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=0.2,
            random_state=42,
            stratify=y
        )

        models = {
            'Logistic Regression': Pipeline([
                ('scaler', StandardScaler()),
                (
                    'model',
                    LogisticRegression(
                        max_iter=1000,
                        class_weight='balanced',
                        random_state=42
                    )
                )
            ]),

            'Decision Tree': DecisionTreeClassifier(
                random_state=42,
                class_weight='balanced',
                max_depth=8
            ),

            'Random Forest': RandomForestClassifier(
                n_estimators=200,
                random_state=42,
                class_weight='balanced',
                max_depth=None
            ),

            'Gradient Boosting': GradientBoostingClassifier(
                n_estimators=200,
                learning_rate=0.05,
                max_depth=3,
                random_state=42
            ),

            'XGBoost': XGBClassifier(
                n_estimators=200,
                learning_rate=0.05,
                max_depth=4,
                subsample=0.8,
                colsample_bytree=0.8,
                eval_metric='logloss',
                random_state=42
            ),

            'KNN': Pipeline([
                ('scaler', StandardScaler()),
                (
                    'model',
                    KNeighborsClassifier(
                        n_neighbors=5
                    )
                )
            ]),

            'Naive Bayes': GaussianNB(),

            'SVM': Pipeline([
                ('scaler', StandardScaler()),
                (
                    'model',
                    SVC(
                        probability=True,
                        class_weight='balanced',
                        random_state=42
                    )
                )
            ]),
        }

        results = []

        best_model_name = None
        best_model = None
        best_f1 = -1

        self.stdout.write('\nModel Comparison Results')
        self.stdout.write('-' * 110)

        for name, model in models.items():
            self.stdout.write(f'\nTraining {name}...')

            model.fit(X_train, y_train)

            y_pred = model.predict(X_test)

            try:
                y_prob = model.predict_proba(X_test)[:, 1]
                roc_auc = roc_auc_score(y_test, y_prob)
            except Exception:
                roc_auc = 0

            accuracy = accuracy_score(y_test, y_pred)

            precision = precision_score(
                y_test,
                y_pred,
                zero_division=0
            )

            recall = recall_score(
                y_test,
                y_pred,
                zero_division=0
            )

            f1 = f1_score(
                y_test,
                y_pred,
                zero_division=0
            )

            results.append({
                'model': name,
                'accuracy': round(accuracy, 4),
                'precision': round(precision, 4),
                'recall': round(recall, 4),
                'f1_score': round(f1, 4),
                'roc_auc': round(roc_auc, 4),
            })

            self.stdout.write(
                f"{name:22} | "
                f"Accuracy: {accuracy:.4f} | "
                f"Precision: {precision:.4f} | "
                f"Recall: {recall:.4f} | "
                f"F1: {f1:.4f} | "
                f"ROC-AUC: {roc_auc:.4f}"
            )

            if f1 > best_f1:
                best_f1 = f1
                best_model_name = name
                best_model = model

        self.stdout.write('-' * 110)

        results_df = pd.DataFrame(results).sort_values(
            by='f1_score',
            ascending=False
        )

        datasets_dir = os.path.join(
            settings.BASE_DIR,
            'datasets'
        )

        os.makedirs(
            datasets_dir,
            exist_ok=True
        )

        results_path = os.path.join(
            datasets_dir,
            'model_comparison_results.csv'
        )

        results_df.to_csv(
            results_path,
            index=False
        )

        model_dir = os.path.join(
            settings.BASE_DIR,
            'ml_models'
        )

        os.makedirs(
            model_dir,
            exist_ok=True
        )

        best_model_path = os.path.join(
            model_dir,
            'best_churn_model.pkl'
        )

        joblib.dump(
            best_model,
            best_model_path
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nBest model based on F1-score: {best_model_name}'
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Best F1-score: {best_f1:.4f}'
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Best model saved at: {best_model_path}'
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Model comparison CSV saved at: {results_path}'
            )
        )

        self.stdout.write('\nSorted Results:')
        self.stdout.write(results_df.to_string(index=False))

        self.stdout.write('\nDetailed classification report for best model:')

        best_predictions = best_model.predict(X_test)

        self.stdout.write(
            classification_report(
                y_test,
                best_predictions,
                zero_division=0
            )
        )