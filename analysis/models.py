# -*- coding: utf-8 -*-
"""Modelos de classificação e regressão com validação cruzada AGRUPADA.

Replica a metodologia dos teus scripts _GROUPED: o split/CV é agrupado por
amostra física (EnsaioId), para evitar fuga de informação (data leakage)
entre réplicas da mesma amostra.

  - Classificação: StratifiedGroupKFold + GridSearchCV aninhado agrupado.
    Modelos: Regressão Logística, PLS-DA, SVM-RBF, Random Forest (+XGBoost se disponível).
    Métricas: accuracy, F1 macro, AUC (binário ou macro-OVR).
  - Regressão: GroupKFold + GridSearchCV aninhado.
    Modelos: PLS, Ridge, SVR-RBF, Random Forest, Gradient Boosting.
    Métricas: R², RMSE.

Grelhas pequenas por defeito (quick=True) para correr depressa; quick=False
usa grelhas maiores (correr no portátil/servidor, não no Pi).
"""
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.svm import SVC, SVR
from sklearn.ensemble import (RandomForestClassifier, RandomForestRegressor,
                              GradientBoostingRegressor)
from sklearn.cross_decomposition import PLSRegression
from sklearn.model_selection import (StratifiedGroupKFold, GroupKFold,
                                     GridSearchCV)
from sklearn.metrics import (accuracy_score, f1_score, roc_auc_score,
                             confusion_matrix, r2_score, mean_squared_error)
from sklearn.base import BaseEstimator, ClassifierMixin

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except Exception:
    HAS_XGB = False


# --- PLS-DA: PLSRegression sobre alvos one-hot + argmax ---------------------
class PLSDA(BaseEstimator, ClassifierMixin):
    def __init__(self, n_components=2):
        self.n_components = n_components

    def fit(self, X, y):
        self.classes_ = np.unique(y)
        Y = np.zeros((len(y), len(self.classes_)))
        for i, c in enumerate(self.classes_):
            Y[y == c, i] = 1
        nc = min(self.n_components, X.shape[1], max(1, len(self.classes_)))
        self.pls_ = PLSRegression(n_components=max(1, nc)).fit(X, Y)
        return self

    def predict(self, X):
        return self.classes_[np.argmax(self.pls_.predict(X), axis=1)]

    def predict_proba(self, X):
        s = self.pls_.predict(X)
        s = s - s.min(axis=1, keepdims=True)
        tot = s.sum(axis=1, keepdims=True)
        tot[tot == 0] = 1
        return s / tot


def _pipe(model):
    return Pipeline([("scaler", StandardScaler()), ("model", model)])


def _clf_models(quick=True):
    if quick:
        grids = {
            "LogReg": (_pipe(LogisticRegression(max_iter=2000, class_weight="balanced")),
                       {"model__C": [0.1, 1, 10]}),
            "PLS-DA": (_pipe(PLSDA()), {"model__n_components": [2, 3, 5]}),
            "SVM-RBF": (_pipe(SVC(kernel="rbf", probability=True, class_weight="balanced")),
                        {"model__C": [1, 10], "model__gamma": ["scale"]}),
            "RandomForest": (_pipe(RandomForestClassifier(n_estimators=200, class_weight="balanced")),
                             {"model__max_depth": [None, 5]}),
        }
    else:
        grids = {
            "LogReg": (_pipe(LogisticRegression(max_iter=5000, class_weight="balanced")),
                       {"model__C": [0.01, 0.1, 1, 10, 100]}),
            "PLS-DA": (_pipe(PLSDA()), {"model__n_components": [2, 3, 4, 5, 6, 8]}),
            "SVM-RBF": (_pipe(SVC(kernel="rbf", probability=True, class_weight="balanced")),
                        {"model__C": [0.1, 1, 10, 100], "model__gamma": ["scale", 0.01, 0.1]}),
            "RandomForest": (_pipe(RandomForestClassifier(n_estimators=400, class_weight="balanced")),
                             {"model__max_depth": [None, 5, 10], "model__min_samples_leaf": [1, 2]}),
        }
        if HAS_XGB:
            grids["XGBoost"] = (_pipe(XGBClassifier(eval_metric="logloss", tree_method="hist")),
                                {"model__max_depth": [3, 5], "model__n_estimators": [200, 400]})
    return grids


def _reg_models(quick=True):
    if quick:
        return {
            "PLS": (_pipe(PLSRegression()), {"model__n_components": [2, 3, 5]}),
            "Ridge": (_pipe(Ridge()), {"model__alpha": [0.1, 1, 10]}),
            "SVR-RBF": (_pipe(SVR(kernel="rbf")), {"model__C": [1, 10], "model__gamma": ["scale"]}),
            "RandomForest": (_pipe(RandomForestRegressor(n_estimators=200)),
                             {"model__max_depth": [None, 5]}),
        }
    return {
        "PLS": (_pipe(PLSRegression()), {"model__n_components": [2, 3, 4, 5, 6, 8, 10]}),
        "Ridge": (_pipe(Ridge()), {"model__alpha": [0.01, 0.1, 1, 10, 100]}),
        "SVR-RBF": (_pipe(SVR(kernel="rbf")),
                    {"model__C": [0.1, 1, 10, 100], "model__gamma": ["scale", 0.01, 0.1]}),
        "RandomForest": (_pipe(RandomForestRegressor(n_estimators=400)),
                         {"model__max_depth": [None, 5, 10], "model__min_samples_leaf": [1, 2]}),
        "GradBoost": (_pipe(GradientBoostingRegressor()),
                      {"model__n_estimators": [200, 400], "model__max_depth": [2, 3]}),
    }


def _auc(y, proba, classes):
    try:
        if len(classes) == 2:
            return roc_auc_score(y, proba[:, 1])
        return roc_auc_score(y, proba, multi_class="ovr", average="macro")
    except Exception:
        return np.nan


def run_classification(df, feature_cols, target_col, group_col="EnsaioId",
                       quick=True, n_splits=5, progress=None):
    data = df.dropna(subset=feature_cols + [target_col, group_col]).copy()
    X = np.asarray(data[feature_cols].to_numpy(), dtype=float)
    y = np.asarray(data[target_col].astype(str).tolist(), dtype=object)
    groups = np.asarray(data[group_col].tolist())
    classes = np.unique(y)

    # nº de folds limitado pelo menor nº de grupos numa classe
    grp_by_class = {}
    for g, lab in zip(groups, y):
        grp_by_class.setdefault(lab, set()).add(g)
    min_groups = min(len(s) for s in grp_by_class.values())
    folds = max(2, min(n_splits, min_groups))

    outer = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=42)
    inner = StratifiedGroupKFold(n_splits=max(2, folds - 1), shuffle=True, random_state=1)

    results = {}
    models = _clf_models(quick)
    for mi, (name, (est, grid)) in enumerate(models.items()):
        accs, f1s, aucs, tr_accs = [], [], [], []
        y_true_all, y_pred_all = [], []
        try:
            for tr, te in outer.split(X, y, groups):
                gs = GridSearchCV(est, grid, cv=inner, scoring="f1_macro", n_jobs=-1)
                gs.fit(X[tr], y[tr], groups=groups[tr])
                best = gs.best_estimator_
                yp = best.predict(X[te])
                tr_accs.append(accuracy_score(y[tr], best.predict(X[tr])))  # treino
                accs.append(accuracy_score(y[te], yp))
                f1s.append(f1_score(y[te], yp, average="macro"))
                if hasattr(best, "predict_proba"):
                    aucs.append(_auc(y[te], best.predict_proba(X[te]), classes))
                y_true_all.extend(y[te]); y_pred_all.extend(yp)
            results[name] = {
                "accuracy": float(np.mean(accs)), "accuracy_sd": float(np.std(accs)),
                "train_accuracy": float(np.mean(tr_accs)),
                "f1_macro": float(np.mean(f1s)),
                "auc": float(np.nanmean(aucs)) if aucs else np.nan,
                "cm": confusion_matrix(y_true_all, y_pred_all, labels=classes),
                "labels": list(classes),
            }
        except Exception as e:
            results[name] = {"error": str(e)}
        if progress:
            progress((mi + 1) / len(models))
    return {"folds": folds, "n_samples": len(np.unique(groups)),
            "results": results, "classes": list(classes)}


def run_regression(df, feature_cols, target_col, group_col="EnsaioId",
                   quick=True, n_splits=5, progress=None):
    data = df.dropna(subset=feature_cols + [target_col, group_col]).copy()
    data = data[pd.to_numeric(data[target_col], errors="coerce").notna()]
    X = np.asarray(data[feature_cols].to_numpy(), dtype=float)
    y = np.asarray(pd.to_numeric(data[target_col]).tolist(), dtype=float)
    groups = np.asarray(data[group_col].tolist())
    n_groups = len(np.unique(groups))
    folds = max(2, min(n_splits, n_groups))

    outer = GroupKFold(n_splits=folds)
    inner = GroupKFold(n_splits=max(2, folds - 1))

    results = {}
    models = _reg_models(quick)
    for mi, (name, (est, grid)) in enumerate(models.items()):
        try:
            y_true_all, y_pred_all, r2s, rmses, tr_r2s = [], [], [], [], []
            for tr, te in outer.split(X, y, groups):
                gs = GridSearchCV(est, grid, cv=inner, scoring="r2", n_jobs=-1)
                gs.fit(X[tr], y[tr], groups=groups[tr])
                yp = gs.best_estimator_.predict(X[te]).ravel()
                tr_r2s.append(r2_score(y[tr], gs.best_estimator_.predict(X[tr]).ravel()))
                r2s.append(r2_score(y[te], yp))
                rmses.append(np.sqrt(mean_squared_error(y[te], yp)))
                y_true_all.extend(y[te]); y_pred_all.extend(yp)
            results[name] = {
                "r2": float(np.mean(r2s)), "r2_sd": float(np.std(r2s)),
                "train_r2": float(np.mean(tr_r2s)),
                "rmse": float(np.mean(rmses)),
                "y_true": list(map(float, y_true_all)),
                "y_pred": list(map(float, y_pred_all)),
            }
        except Exception as e:
            results[name] = {"error": str(e)}
        if progress:
            progress((mi + 1) / len(models))
    return {"folds": folds, "n_samples": n_groups, "results": results}


# ---------------------------------------------------------------------------
# Persistência do modelo (base para a futura página de Inferência)
# ---------------------------------------------------------------------------
def fit_full_model(df, feature_cols, target_col, task, model_name, quick=True):
    """Ajusta o modelo escolhido a TODOS os dados (após seleção de hiperparâmetros
    por CV agrupada) e devolve o estimador final + metadados."""
    data = df.dropna(subset=feature_cols + [target_col]).copy()
    X = np.asarray(data[feature_cols].to_numpy(), dtype=float)
    groups = np.asarray(data["EnsaioId"].tolist()) if "EnsaioId" in data else None
    if task == "classification":
        y = np.asarray(data[target_col].astype(str).tolist(), dtype=object)
        est, grid = _clf_models(quick)[model_name]
        n = max(2, min(5, min(len(set(groups[y == c])) for c in np.unique(y)))) if groups is not None else 5
        cv = StratifiedGroupKFold(n_splits=n, shuffle=True, random_state=1)
        gs = GridSearchCV(est, grid, cv=cv, scoring="f1_macro", n_jobs=-1)
        gs.fit(X, y, groups=groups)
    else:
        y = np.asarray(pd.to_numeric(data[target_col]).tolist(), dtype=float)
        est, grid = _reg_models(quick)[model_name]
        n = max(2, min(5, len(np.unique(groups)))) if groups is not None else 5
        cv = GroupKFold(n_splits=n)
        gs = GridSearchCV(est, grid, cv=cv, scoring="r2", n_jobs=-1)
        gs.fit(X, y, groups=groups)
    return gs.best_estimator_, {"task": task, "target": target_col,
                                "features": feature_cols, "model": model_name,
                                "best_params": gs.best_params_}


def save_model(estimator, meta, path):
    import joblib
    joblib.dump({"estimator": estimator, "meta": meta}, path)
    return path


def load_model(path):
    import joblib
    d = joblib.load(path)
    return d["estimator"], d["meta"]
