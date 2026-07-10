from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.discriminant_analysis import (
    LinearDiscriminantAnalysis,
    QuadraticDiscriminantAnalysis,
)
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import (
    AdaBoostClassifier,
    AdaBoostRegressor,
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import (
    ElasticNet,
    HuberRegressor,
    Lasso,
    LinearRegression,
    LogisticRegression,
    Perceptron,
    PoissonRegressor,
    QuantileRegressor,
    Ridge,
    RidgeClassifier,
    SGDClassifier,
    SGDRegressor,
    TweedieRegressor,
)
from sklearn.naive_bayes import BernoulliNB, ComplementNB, GaussianNB
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import LinearSVC, LinearSVR, NuSVC, NuSVR, SVC, SVR
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

ProblemType = Literal[
    "binary_classification",
    "multiclass_classification",
    "regression",
]
ExecutionMode = Literal["incremental", "in_memory"]
ParameterKind = Literal["integer", "number", "boolean", "select", "integer_list"]


@dataclass(frozen=True)
class ParameterSpec:
    id: str
    label: str
    kind: ParameterKind
    default: Any
    description: str = ""
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    options: tuple[Any, ...] = ()
    nullable: bool = False
    search: dict[str, Any] | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "default": self.default,
            "description": self.description,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "step": self.step,
            "options": list(self.options),
            "nullable": self.nullable,
            "search": self.search,
        }


@dataclass(frozen=True)
class AlgorithmSpec:
    id: str
    label: str
    family: str
    problem_types: tuple[ProblemType, ...]
    description: str
    execution_mode: ExecutionMode
    scale_profile: Literal["streaming", "large", "medium", "small"]
    parameters: tuple[ParameterSpec, ...] = ()
    dependency: str = "scikit-learn"
    supports_probability: bool = False
    supports_early_stopping: bool = False
    automl_default: bool = False
    notes: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        module = {
            "XGBoost": "xgboost",
            "LightGBM": "lightgbm",
            "CatBoost": "catboost",
        }.get(self.dependency)
        return module is None or importlib.util.find_spec(module) is not None

    def defaults(self) -> dict[str, Any]:
        return {parameter.id: parameter.default for parameter in self.parameters}

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "family": self.family,
            "problem_types": list(self.problem_types),
            "description": self.description,
            "execution_mode": self.execution_mode,
            "scale_profile": self.scale_profile,
            "dependency": self.dependency,
            "available": self.available,
            "supports_probability": self.supports_probability,
            "supports_early_stopping": self.supports_early_stopping,
            "automl_default": self.automl_default,
            "notes": list(self.notes),
            "parameters": [parameter.public_dict() for parameter in self.parameters],
        }


def _int(
    id: str,
    label: str,
    default: int | None,
    minimum: int,
    maximum: int,
    *,
    step: int = 1,
    nullable: bool = False,
    search: dict[str, Any] | None = None,
    description: str = "",
) -> ParameterSpec:
    return ParameterSpec(
        id=id,
        label=label,
        kind="integer",
        default=default,
        minimum=minimum,
        maximum=maximum,
        step=step,
        nullable=nullable,
        search=search,
        description=description,
    )


def _float(
    id: str,
    label: str,
    default: float,
    minimum: float,
    maximum: float,
    *,
    step: float | None = None,
    search: dict[str, Any] | None = None,
    description: str = "",
) -> ParameterSpec:
    return ParameterSpec(
        id=id,
        label=label,
        kind="number",
        default=default,
        minimum=minimum,
        maximum=maximum,
        step=step,
        search=search,
        description=description,
    )


def _bool(id: str, label: str, default: bool, description: str = "") -> ParameterSpec:
    return ParameterSpec(
        id=id,
        label=label,
        kind="boolean",
        default=default,
        description=description,
    )


def _select(
    id: str,
    label: str,
    default: Any,
    options: tuple[Any, ...],
    *,
    nullable: bool = False,
    search: dict[str, Any] | None = None,
    description: str = "",
) -> ParameterSpec:
    return ParameterSpec(
        id=id,
        label=label,
        kind="select",
        default=default,
        options=options,
        nullable=nullable,
        search=search,
        description=description,
    )


CLASSIFICATION = ("binary_classification", "multiclass_classification")
REGRESSION = ("regression",)
CLASS_WEIGHT = _select(
    "class_weight",
    "Class weighting",
    None,
    (None, "balanced"),
    nullable=True,
    search={"kind": "categorical", "values": [None, "balanced"]},
)
FIT_INTERCEPT = _bool("fit_intercept", "Fit intercept", True)
ALPHA = _float(
    "alpha",
    "Regularization alpha",
    0.0001,
    0.0,
    100.0,
    step=0.0001,
    search={"kind": "float", "low": 1e-7, "high": 1e-1, "log": True},
)
C_PARAMETER = _float(
    "C",
    "Regularization C",
    1.0,
    1e-6,
    1e6,
    search={"kind": "float", "low": 1e-4, "high": 1e3, "log": True},
)
N_ESTIMATORS = _int(
    "n_estimators",
    "Number of estimators",
    300,
    10,
    5000,
    step=10,
    search={"kind": "int", "low": 100, "high": 1000, "step": 100},
)
MAX_DEPTH = _int(
    "max_depth",
    "Maximum tree depth",
    None,
    1,
    100,
    nullable=True,
    search={"kind": "categorical", "values": [None, 4, 8, 16, 32]},
)
MIN_SAMPLES_SPLIT = _int(
    "min_samples_split",
    "Minimum samples to split",
    2,
    2,
    1000,
    search={"kind": "int", "low": 2, "high": 30},
)
MIN_SAMPLES_LEAF = _int(
    "min_samples_leaf",
    "Minimum samples per leaf",
    1,
    1,
    1000,
    search={"kind": "int", "low": 1, "high": 20},
)
MAX_FEATURES = _select(
    "max_features",
    "Features per split",
    "sqrt",
    ("sqrt", "log2", None),
    nullable=True,
    search={"kind": "categorical", "values": ["sqrt", "log2", None]},
)
LEARNING_RATE = _float(
    "learning_rate",
    "Learning rate",
    0.05,
    1e-4,
    1.0,
    step=0.01,
    search={"kind": "float", "low": 0.005, "high": 0.3, "log": True},
)

SGD_CLASSIFIER_PARAMETERS = (
    _select(
        "loss",
        "Loss",
        "log_loss",
        ("log_loss", "modified_huber", "hinge", "squared_hinge", "perceptron"),
        search={"kind": "categorical", "values": ["log_loss", "modified_huber", "hinge"]},
    ),
    ALPHA,
    _select(
        "penalty",
        "Penalty",
        "l2",
        (None, "l2", "l1", "elasticnet"),
        nullable=True,
        search={"kind": "categorical", "values": ["l2", "l1", "elasticnet"]},
    ),
    _float(
        "l1_ratio",
        "Elastic-net L1 ratio",
        0.15,
        0.0,
        1.0,
        step=0.05,
        search={"kind": "float", "low": 0.0, "high": 1.0},
    ),
    _select(
        "learning_rate",
        "Learning-rate schedule",
        "optimal",
        ("optimal", "constant", "invscaling", "adaptive"),
    ),
    _float("eta0", "Initial learning rate", 0.01, 1e-7, 10.0, step=0.001),
    FIT_INTERCEPT,
    CLASS_WEIGHT,
)
SGD_REGRESSOR_PARAMETERS = (
    _select(
        "loss",
        "Loss",
        "squared_error",
        ("squared_error", "huber", "epsilon_insensitive", "squared_epsilon_insensitive"),
        search={"kind": "categorical", "values": ["squared_error", "huber", "epsilon_insensitive"]},
    ),
    *SGD_CLASSIFIER_PARAMETERS[1:7],
    _float("epsilon", "Epsilon", 0.1, 0.0, 1000.0, step=0.01),
)
MLP_PARAMETERS = (
    ParameterSpec(
        id="hidden_layer_sizes",
        label="Hidden layer sizes",
        kind="integer_list",
        default=[128, 64],
        description="Comma-separated dense layer widths, for example 256, 128, 32.",
        search={
            "kind": "categorical",
            "values": [[64], [128], [128, 64], [256, 128], [256, 128, 64]],
        },
    ),
    _select(
        "activation",
        "Activation",
        "relu",
        ("relu", "tanh", "logistic"),
        search={"kind": "categorical", "values": ["relu", "tanh"]},
    ),
    _select("solver", "Optimizer", "adam", ("adam", "sgd", "lbfgs")),
    _float(
        "alpha",
        "L2 regularization",
        0.0001,
        0.0,
        100.0,
        search={"kind": "float", "low": 1e-7, "high": 1e-1, "log": True},
    ),
    _float(
        "learning_rate_init",
        "Initial learning rate",
        0.001,
        1e-6,
        1.0,
        search={"kind": "float", "low": 1e-5, "high": 1e-1, "log": True},
    ),
    _int("max_iter", "Maximum iterations", 300, 10, 5000, step=10),
    _bool("early_stopping", "Internal early stopping", True),
)
FOREST_PARAMETERS = (
    N_ESTIMATORS,
    MAX_DEPTH,
    MIN_SAMPLES_SPLIT,
    MIN_SAMPLES_LEAF,
    MAX_FEATURES,
    _bool("bootstrap", "Bootstrap rows", True),
)
BOOST_PARAMETERS = (
    N_ESTIMATORS,
    LEARNING_RATE,
    _int(
        "max_depth",
        "Maximum tree depth",
        3,
        1,
        32,
        search={"kind": "int", "low": 2, "high": 10},
    ),
    _float(
        "subsample",
        "Row subsample",
        1.0,
        0.1,
        1.0,
        step=0.05,
        search={"kind": "float", "low": 0.5, "high": 1.0},
    ),
)
HIST_PARAMETERS = (
    LEARNING_RATE,
    _int(
        "max_iter",
        "Boosting iterations",
        300,
        10,
        5000,
        step=10,
        search={"kind": "int", "low": 100, "high": 1000, "step": 100},
    ),
    _int(
        "max_leaf_nodes",
        "Maximum leaf nodes",
        31,
        2,
        1024,
        search={"kind": "int", "low": 15, "high": 255},
    ),
    MAX_DEPTH,
    _float(
        "l2_regularization",
        "L2 regularization",
        0.0,
        0.0,
        1000.0,
        search={"kind": "float", "low": 1e-8, "high": 10.0, "log": True},
    ),
)
EXTERNAL_BOOST_PARAMETERS = (
    N_ESTIMATORS,
    LEARNING_RATE,
    _int(
        "max_depth",
        "Maximum tree depth",
        6,
        1,
        32,
        search={"kind": "int", "low": 3, "high": 12},
    ),
    _float(
        "subsample",
        "Row subsample",
        0.9,
        0.1,
        1.0,
        step=0.05,
        search={"kind": "float", "low": 0.5, "high": 1.0},
    ),
    _float(
        "colsample_bytree",
        "Column subsample",
        0.9,
        0.1,
        1.0,
        step=0.05,
        search={"kind": "float", "low": 0.5, "high": 1.0},
    ),
    _float(
        "reg_alpha",
        "L1 regularization",
        0.0,
        0.0,
        1000.0,
        search={"kind": "float", "low": 1e-8, "high": 10.0, "log": True},
    ),
    _float(
        "reg_lambda",
        "L2 regularization",
        1.0,
        0.0,
        1000.0,
        search={"kind": "float", "low": 1e-8, "high": 100.0, "log": True},
    ),
)


def _algorithm_specs() -> tuple[AlgorithmSpec, ...]:
    return (
        AlgorithmSpec(
            "dummy_classifier",
            "Dummy classifier (baseline)",
            "Baselines",
            CLASSIFICATION,
            "A mandatory sanity-check baseline using the class distribution.",
            "in_memory",
            "large",
            (_select("strategy", "Strategy", "prior", ("prior", "most_frequent", "stratified")),),
            supports_probability=True,
        ),
        AlgorithmSpec(
            "logistic_regression",
            "Logistic regression",
            "Linear models",
            CLASSIFICATION,
            "Regularized probabilistic linear classifier with strong, interpretable baselines.",
            "in_memory",
            "large",
            (
                C_PARAMETER,
                _select(
                    "penalty",
                    "Penalty",
                    "l2",
                    ("l2", "l1", "elasticnet"),
                    search={"kind": "categorical", "values": ["l2", "l1", "elasticnet"]},
                ),
                _float("l1_ratio", "Elastic-net L1 ratio", 0.5, 0.0, 1.0, step=0.05),
                _int("max_iter", "Maximum iterations", 1000, 50, 10000, step=50),
                CLASS_WEIGHT,
                FIT_INTERCEPT,
            ),
            supports_probability=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "ridge_classifier",
            "Ridge classifier",
            "Linear models",
            CLASSIFICATION,
            "Fast L2-regularized linear classifier suitable for wide numeric feature matrices.",
            "in_memory",
            "large",
            (
                _float(
                    "alpha",
                    "Regularization alpha",
                    1.0,
                    1e-8,
                    1e6,
                    search={"kind": "float", "low": 1e-5, "high": 1e3, "log": True},
                ),
                CLASS_WEIGHT,
                FIT_INTERCEPT,
            ),
            automl_default=True,
        ),
        AlgorithmSpec(
            "sgd_classifier",
            "Incremental linear classifier (SGD)",
            "Online / large-scale",
            CLASSIFICATION,
            "Streaming linear classifier trained over the complete relation in bounded batches.",
            "incremental",
            "streaming",
            SGD_CLASSIFIER_PARAMETERS,
            supports_probability=True,
            supports_early_stopping=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "passive_aggressive_classifier",
            "Passive-Aggressive classifier",
            "Online / large-scale",
            CLASSIFICATION,
            "Fast margin-based online learner for high-volume sparse or dense feature streams.",
            "incremental",
            "streaming",
            (
                C_PARAMETER,
                _select(
                    "loss",
                    "Loss",
                    "hinge",
                    ("hinge", "squared_hinge"),
                    search={"kind": "categorical", "values": ["hinge", "squared_hinge"]},
                ),
                _bool("average", "Average weights", False),
                FIT_INTERCEPT,
                CLASS_WEIGHT,
            ),
            supports_early_stopping=True,
        ),
        AlgorithmSpec(
            "perceptron_classifier",
            "Perceptron classifier",
            "Online / large-scale",
            CLASSIFICATION,
            "Classic online linear threshold classifier.",
            "incremental",
            "streaming",
            (
                ALPHA,
                _select("penalty", "Penalty", None, (None, "l2", "l1", "elasticnet"), nullable=True),
                _float("eta0", "Learning rate", 1.0, 1e-6, 1000.0, step=0.1),
                FIT_INTERCEPT,
                CLASS_WEIGHT,
            ),
            supports_early_stopping=True,
        ),
        AlgorithmSpec(
            "linear_svc",
            "Linear SVM",
            "Support vector machines",
            CLASSIFICATION,
            "Linear maximum-margin classifier; efficient for wide datasets.",
            "in_memory",
            "large",
            (C_PARAMETER, CLASS_WEIGHT, _int("max_iter", "Maximum iterations", 5000, 100, 100000, step=100)),
            automl_default=True,
        ),
        AlgorithmSpec(
            "svc_rbf",
            "Kernel SVM (RBF)",
            "Support vector machines",
            CLASSIFICATION,
            "Non-linear radial-basis SVM. Powerful on smaller datasets, with super-linear cost.",
            "in_memory",
            "small",
            (
                C_PARAMETER,
                _select(
                    "gamma",
                    "Kernel gamma",
                    "scale",
                    ("scale", "auto"),
                ),
                _bool("probability", "Probability calibration", True),
                CLASS_WEIGHT,
            ),
            supports_probability=True,
            notes=("Training cost grows at least quadratically for many datasets.",),
        ),
        AlgorithmSpec(
            "svc_poly",
            "Kernel SVM (polynomial)",
            "Support vector machines",
            CLASSIFICATION,
            "Polynomial-kernel SVM for explicit non-linear interactions.",
            "in_memory",
            "small",
            (
                C_PARAMETER,
                _int("degree", "Polynomial degree", 3, 2, 10),
                _select("gamma", "Kernel gamma", "scale", ("scale", "auto")),
                _bool("probability", "Probability calibration", True),
                CLASS_WEIGHT,
            ),
            supports_probability=True,
            notes=("Training cost grows at least quadratically for many datasets.",),
        ),
        AlgorithmSpec(
            "nu_svc",
            "Nu-SVM classifier",
            "Support vector machines",
            CLASSIFICATION,
            "Alternative kernel SVM parameterized by the support-vector fraction.",
            "in_memory",
            "small",
            (
                _float(
                    "nu",
                    "Nu",
                    0.5,
                    0.001,
                    0.999,
                    step=0.01,
                    search={"kind": "float", "low": 0.05, "high": 0.9},
                ),
                _select("kernel", "Kernel", "rbf", ("rbf", "poly", "sigmoid")),
                _select("gamma", "Kernel gamma", "scale", ("scale", "auto")),
                _bool("probability", "Probability calibration", True),
                CLASS_WEIGHT,
            ),
            supports_probability=True,
            notes=("Training cost grows at least quadratically for many datasets.",),
        ),
        AlgorithmSpec(
            "decision_tree_classifier",
            "Decision tree classifier",
            "Trees",
            CLASSIFICATION,
            "Interpretable non-linear tree with explicit depth and leaf regularization.",
            "in_memory",
            "medium",
            (
                _select("criterion", "Split criterion", "gini", ("gini", "entropy", "log_loss")),
                MAX_DEPTH,
                MIN_SAMPLES_SPLIT,
                MIN_SAMPLES_LEAF,
                MAX_FEATURES,
                CLASS_WEIGHT,
            ),
            supports_probability=True,
        ),
        AlgorithmSpec(
            "random_forest_classifier",
            "Random forest classifier",
            "Tree ensembles",
            CLASSIFICATION,
            "Bagged decision trees with robust non-linear performance and feature importance.",
            "in_memory",
            "medium",
            (*FOREST_PARAMETERS, CLASS_WEIGHT),
            supports_probability=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "extra_trees_classifier",
            "Extremely randomized trees classifier",
            "Tree ensembles",
            CLASSIFICATION,
            "Highly randomized tree ensemble; fast and often competitive on tabular data.",
            "in_memory",
            "medium",
            (*FOREST_PARAMETERS[:-1], CLASS_WEIGHT),
            supports_probability=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "gradient_boosting_classifier",
            "Gradient boosting classifier",
            "Boosting",
            CLASSIFICATION,
            "Classic stage-wise gradient boosting over shallow regression trees.",
            "in_memory",
            "medium",
            BOOST_PARAMETERS,
            supports_probability=True,
        ),
        AlgorithmSpec(
            "hist_gradient_boosting_classifier",
            "Histogram gradient boosting classifier",
            "Boosting",
            CLASSIFICATION,
            "Histogram-based boosting optimized for larger tabular datasets.",
            "in_memory",
            "large",
            (*HIST_PARAMETERS, _select("class_weight", "Class weighting", None, (None, "balanced"), nullable=True)),
            supports_probability=True,
            supports_early_stopping=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "ada_boost_classifier",
            "AdaBoost classifier",
            "Boosting",
            CLASSIFICATION,
            "Adaptive boosting baseline emphasizing previously misclassified observations.",
            "in_memory",
            "medium",
            (N_ESTIMATORS, LEARNING_RATE),
            supports_probability=True,
        ),
        AlgorithmSpec(
            "knn_classifier",
            "k-nearest neighbours classifier",
            "Neighbour methods",
            CLASSIFICATION,
            "Instance-based non-linear classifier; prediction retains the full training set.",
            "in_memory",
            "small",
            (
                _int(
                    "n_neighbors",
                    "Number of neighbours",
                    5,
                    1,
                    1000,
                    search={"kind": "int", "low": 3, "high": 51, "step": 2},
                ),
                _select("weights", "Neighbour weighting", "uniform", ("uniform", "distance")),
                _select("p", "Minkowski power", 2, (1, 2)),
            ),
            supports_probability=True,
        ),
        AlgorithmSpec(
            "gaussian_nb",
            "Gaussian Naive Bayes",
            "Probabilistic",
            CLASSIFICATION,
            "Fast generative classifier for approximately Gaussian numeric features.",
            "in_memory",
            "large",
            (
                _float(
                    "var_smoothing",
                    "Variance smoothing",
                    1e-9,
                    1e-15,
                    1.0,
                    search={"kind": "float", "low": 1e-12, "high": 1e-6, "log": True},
                ),
            ),
            supports_probability=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "bernoulli_nb",
            "Bernoulli Naive Bayes",
            "Probabilistic",
            CLASSIFICATION,
            "Naive Bayes for binary or thresholded feature matrices.",
            "in_memory",
            "large",
            (
                _float(
                    "alpha",
                    "Additive smoothing",
                    1.0,
                    0.0,
                    1000.0,
                    search={"kind": "float", "low": 1e-4, "high": 100.0, "log": True},
                ),
                _float("binarize", "Binarization threshold", 0.0, -1e6, 1e6),
                _bool("fit_prior", "Learn class prior", True),
            ),
            supports_probability=True,
        ),
        AlgorithmSpec(
            "complement_nb",
            "Complement Naive Bayes",
            "Probabilistic",
            CLASSIFICATION,
            "Naive Bayes variant robust to imbalanced classes; requires non-negative features.",
            "in_memory",
            "large",
            (
                _float(
                    "alpha",
                    "Additive smoothing",
                    1.0,
                    0.0,
                    1000.0,
                    search={"kind": "float", "low": 1e-4, "high": 100.0, "log": True},
                ),
                _bool("norm", "Normalize weights", False),
            ),
            supports_probability=True,
            notes=("All feature values must be non-negative.",),
        ),
        AlgorithmSpec(
            "lda_classifier",
            "Linear discriminant analysis",
            "Discriminant analysis",
            CLASSIFICATION,
            "Generative linear decision boundary with shared class covariance.",
            "in_memory",
            "medium",
            (
                _select("solver", "Solver", "svd", ("svd", "lsqr", "eigen")),
                _select("shrinkage", "Covariance shrinkage", None, (None, "auto"), nullable=True),
            ),
            supports_probability=True,
        ),
        AlgorithmSpec(
            "qda_classifier",
            "Quadratic discriminant analysis",
            "Discriminant analysis",
            CLASSIFICATION,
            "Class-specific covariance model producing quadratic decision boundaries.",
            "in_memory",
            "small",
            (
                _float(
                    "reg_param",
                    "Covariance regularization",
                    0.0,
                    0.0,
                    1.0,
                    step=0.01,
                    search={"kind": "float", "low": 0.0, "high": 1.0},
                ),
            ),
            supports_probability=True,
        ),
        AlgorithmSpec(
            "mlp_classifier",
            "Multilayer perceptron classifier",
            "Neural networks",
            CLASSIFICATION,
            "Configurable dense feed-forward neural network for numeric tabular features.",
            "in_memory",
            "medium",
            MLP_PARAMETERS,
            supports_probability=True,
            supports_early_stopping=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "xgboost_classifier",
            "XGBoost classifier",
            "Modern boosting",
            CLASSIFICATION,
            "Production-grade regularized gradient tree boosting.",
            "in_memory",
            "large",
            EXTERNAL_BOOST_PARAMETERS,
            dependency="XGBoost",
            supports_probability=True,
            supports_early_stopping=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "lightgbm_classifier",
            "LightGBM classifier",
            "Modern boosting",
            CLASSIFICATION,
            "Leaf-wise histogram gradient boosting optimized for throughput and large tables.",
            "in_memory",
            "large",
            (
                N_ESTIMATORS,
                LEARNING_RATE,
                _int(
                    "num_leaves",
                    "Number of leaves",
                    31,
                    2,
                    4096,
                    search={"kind": "int", "low": 15, "high": 255},
                ),
                MAX_DEPTH,
                *EXTERNAL_BOOST_PARAMETERS[3:],
            ),
            dependency="LightGBM",
            supports_probability=True,
            supports_early_stopping=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "catboost_classifier",
            "CatBoost classifier",
            "Modern boosting",
            CLASSIFICATION,
            "Ordered gradient boosting with robust defaults for tabular learning.",
            "in_memory",
            "large",
            (
                _int(
                    "iterations",
                    "Boosting iterations",
                    500,
                    10,
                    10000,
                    step=10,
                    search={"kind": "int", "low": 200, "high": 1200, "step": 100},
                ),
                LEARNING_RATE,
                _int(
                    "depth",
                    "Tree depth",
                    6,
                    1,
                    16,
                    search={"kind": "int", "low": 4, "high": 10},
                ),
                _float(
                    "l2_leaf_reg",
                    "L2 leaf regularization",
                    3.0,
                    0.0,
                    1000.0,
                    search={"kind": "float", "low": 1e-3, "high": 100.0, "log": True},
                ),
                _float(
                    "random_strength",
                    "Random strength",
                    1.0,
                    0.0,
                    1000.0,
                    search={"kind": "float", "low": 1e-3, "high": 10.0, "log": True},
                ),
            ),
            dependency="CatBoost",
            supports_probability=True,
            supports_early_stopping=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "dummy_regressor",
            "Dummy regressor (baseline)",
            "Baselines",
            REGRESSION,
            "A mandatory mean or median baseline for regression experiments.",
            "in_memory",
            "large",
            (_select("strategy", "Strategy", "mean", ("mean", "median")),),
        ),
        AlgorithmSpec(
            "linear_regression",
            "Ordinary least squares",
            "Linear models",
            REGRESSION,
            "Unregularized linear least-squares regression.",
            "in_memory",
            "large",
            (FIT_INTERCEPT, _bool("positive", "Positive coefficients only", False)),
        ),
        AlgorithmSpec(
            "ridge_regression",
            "Ridge regression",
            "Linear models",
            REGRESSION,
            "L2-regularized linear regression with stable behavior under collinearity.",
            "in_memory",
            "large",
            (
                _float(
                    "alpha",
                    "Regularization alpha",
                    1.0,
                    0.0,
                    1e9,
                    search={"kind": "float", "low": 1e-6, "high": 1e4, "log": True},
                ),
                FIT_INTERCEPT,
                _bool("positive", "Positive coefficients only", False),
            ),
            automl_default=True,
        ),
        AlgorithmSpec(
            "lasso_regression",
            "Lasso regression",
            "Linear models",
            REGRESSION,
            "Sparse L1-regularized linear regression with embedded feature selection.",
            "in_memory",
            "medium",
            (
                _float(
                    "alpha",
                    "Regularization alpha",
                    1.0,
                    1e-10,
                    1e9,
                    search={"kind": "float", "low": 1e-6, "high": 1e3, "log": True},
                ),
                FIT_INTERCEPT,
                _int("max_iter", "Maximum iterations", 5000, 100, 100000, step=100),
                _bool("positive", "Positive coefficients only", False),
            ),
            automl_default=True,
        ),
        AlgorithmSpec(
            "elastic_net_regression",
            "Elastic Net regression",
            "Linear models",
            REGRESSION,
            "Combined L1/L2 regularization for sparse, correlated feature spaces.",
            "in_memory",
            "medium",
            (
                _float(
                    "alpha",
                    "Regularization alpha",
                    1.0,
                    1e-10,
                    1e9,
                    search={"kind": "float", "low": 1e-6, "high": 1e3, "log": True},
                ),
                _float(
                    "l1_ratio",
                    "L1 ratio",
                    0.5,
                    0.0,
                    1.0,
                    step=0.05,
                    search={"kind": "float", "low": 0.0, "high": 1.0},
                ),
                FIT_INTERCEPT,
                _int("max_iter", "Maximum iterations", 5000, 100, 100000, step=100),
                _bool("positive", "Positive coefficients only", False),
            ),
            automl_default=True,
        ),
        AlgorithmSpec(
            "sgd_regressor",
            "Incremental linear regressor (SGD)",
            "Online / large-scale",
            REGRESSION,
            "Streaming linear regression trained over every row in bounded batches.",
            "incremental",
            "streaming",
            SGD_REGRESSOR_PARAMETERS,
            supports_early_stopping=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "passive_aggressive_regressor",
            "Passive-Aggressive regressor",
            "Online / large-scale",
            REGRESSION,
            "Online large-margin regression for high-throughput feature streams.",
            "incremental",
            "streaming",
            (
                C_PARAMETER,
                _float("epsilon", "Epsilon", 0.1, 0.0, 1000.0, step=0.01),
                _select(
                    "loss",
                    "Loss",
                    "epsilon_insensitive",
                    ("epsilon_insensitive", "squared_epsilon_insensitive"),
                ),
                _bool("average", "Average weights", False),
                FIT_INTERCEPT,
            ),
            supports_early_stopping=True,
        ),
        AlgorithmSpec(
            "huber_regressor",
            "Huber robust regression",
            "Robust linear models",
            REGRESSION,
            "Linear regression robust to outliers through Huber loss.",
            "in_memory",
            "medium",
            (
                _float(
                    "epsilon",
                    "Robustness epsilon",
                    1.35,
                    1.0001,
                    100.0,
                    search={"kind": "float", "low": 1.05, "high": 3.0},
                ),
                _float(
                    "alpha",
                    "Regularization alpha",
                    0.0001,
                    0.0,
                    1000.0,
                    search={"kind": "float", "low": 1e-7, "high": 1e-1, "log": True},
                ),
                FIT_INTERCEPT,
                _int("max_iter", "Maximum iterations", 500, 50, 10000, step=50),
            ),
        ),
        AlgorithmSpec(
            "quantile_regressor",
            "Quantile regression",
            "Robust linear models",
            REGRESSION,
            "Conditional quantile model for asymmetric costs and prediction intervals.",
            "in_memory",
            "medium",
            (
                _float("quantile", "Target quantile", 0.5, 0.001, 0.999, step=0.01),
                _float(
                    "alpha",
                    "L1 regularization",
                    1.0,
                    0.0,
                    1e6,
                    search={"kind": "float", "low": 1e-6, "high": 100.0, "log": True},
                ),
                FIT_INTERCEPT,
            ),
        ),
        AlgorithmSpec(
            "poisson_regressor",
            "Poisson regression",
            "Generalized linear models",
            REGRESSION,
            "Log-link generalized linear model for non-negative count-like targets.",
            "in_memory",
            "large",
            (
                _float(
                    "alpha",
                    "L2 regularization",
                    1.0,
                    0.0,
                    1e6,
                    search={"kind": "float", "low": 1e-6, "high": 100.0, "log": True},
                ),
                _int("max_iter", "Maximum iterations", 500, 50, 10000, step=50),
            ),
            notes=("The target must be non-negative.",),
        ),
        AlgorithmSpec(
            "tweedie_regressor",
            "Tweedie regression",
            "Generalized linear models",
            REGRESSION,
            "Power-variance GLM supporting normal, Poisson, gamma and compound distributions.",
            "in_memory",
            "large",
            (
                _float("power", "Tweedie power", 1.5, 0.0, 3.0, step=0.1),
                _float(
                    "alpha",
                    "L2 regularization",
                    1.0,
                    0.0,
                    1e6,
                    search={"kind": "float", "low": 1e-6, "high": 100.0, "log": True},
                ),
                _select("link", "Link function", "auto", ("auto", "identity", "log")),
                _int("max_iter", "Maximum iterations", 500, 50, 10000, step=50),
            ),
        ),
        AlgorithmSpec(
            "linear_svr",
            "Linear SVR",
            "Support vector machines",
            REGRESSION,
            "Linear epsilon-insensitive support vector regression.",
            "in_memory",
            "large",
            (
                C_PARAMETER,
                _float(
                    "epsilon",
                    "Epsilon tube",
                    0.0,
                    0.0,
                    1e6,
                    search={"kind": "float", "low": 1e-4, "high": 1.0, "log": True},
                ),
                _int("max_iter", "Maximum iterations", 10000, 100, 1_000_000, step=100),
            ),
            automl_default=True,
        ),
        AlgorithmSpec(
            "svr_rbf",
            "Kernel SVR (RBF)",
            "Support vector machines",
            REGRESSION,
            "Non-linear radial-basis support vector regression.",
            "in_memory",
            "small",
            (
                C_PARAMETER,
                _float(
                    "epsilon",
                    "Epsilon tube",
                    0.1,
                    0.0,
                    1e6,
                    search={"kind": "float", "low": 1e-4, "high": 1.0, "log": True},
                ),
                _select("gamma", "Kernel gamma", "scale", ("scale", "auto")),
            ),
            notes=("Training cost grows super-linearly and can become cubic.",),
        ),
        AlgorithmSpec(
            "svr_poly",
            "Kernel SVR (polynomial)",
            "Support vector machines",
            REGRESSION,
            "Polynomial-kernel support vector regression.",
            "in_memory",
            "small",
            (
                C_PARAMETER,
                _float("epsilon", "Epsilon tube", 0.1, 0.0, 1e6),
                _int("degree", "Polynomial degree", 3, 2, 10),
                _select("gamma", "Kernel gamma", "scale", ("scale", "auto")),
            ),
            notes=("Training cost grows super-linearly and can become cubic.",),
        ),
        AlgorithmSpec(
            "nu_svr",
            "Nu-SVR",
            "Support vector machines",
            REGRESSION,
            "Kernel support vector regression parameterized by nu.",
            "in_memory",
            "small",
            (
                C_PARAMETER,
                _float(
                    "nu",
                    "Nu",
                    0.5,
                    0.001,
                    0.999,
                    step=0.01,
                    search={"kind": "float", "low": 0.05, "high": 0.9},
                ),
                _select("kernel", "Kernel", "rbf", ("rbf", "poly", "sigmoid")),
                _select("gamma", "Kernel gamma", "scale", ("scale", "auto")),
            ),
            notes=("Training cost grows super-linearly and can become cubic.",),
        ),
        AlgorithmSpec(
            "decision_tree_regressor",
            "Decision tree regressor",
            "Trees",
            REGRESSION,
            "Interpretable piecewise-constant non-linear regression tree.",
            "in_memory",
            "medium",
            (
                _select(
                    "criterion",
                    "Split criterion",
                    "squared_error",
                    ("squared_error", "friedman_mse", "absolute_error", "poisson"),
                ),
                MAX_DEPTH,
                MIN_SAMPLES_SPLIT,
                MIN_SAMPLES_LEAF,
                MAX_FEATURES,
            ),
        ),
        AlgorithmSpec(
            "random_forest_regressor",
            "Random forest regressor",
            "Tree ensembles",
            REGRESSION,
            "Bagged regression trees with strong non-linear baseline performance.",
            "in_memory",
            "medium",
            FOREST_PARAMETERS,
            automl_default=True,
        ),
        AlgorithmSpec(
            "extra_trees_regressor",
            "Extremely randomized trees regressor",
            "Tree ensembles",
            REGRESSION,
            "Randomized tree ensemble that is fast and competitive for tabular regression.",
            "in_memory",
            "medium",
            FOREST_PARAMETERS[:-1],
            automl_default=True,
        ),
        AlgorithmSpec(
            "gradient_boosting_regressor",
            "Gradient boosting regressor",
            "Boosting",
            REGRESSION,
            "Classic stage-wise gradient boosting with multiple robust loss choices.",
            "in_memory",
            "medium",
            (
                *BOOST_PARAMETERS,
                _select("loss", "Loss", "squared_error", ("squared_error", "absolute_error", "huber", "quantile")),
            ),
        ),
        AlgorithmSpec(
            "hist_gradient_boosting_regressor",
            "Histogram gradient boosting regressor",
            "Boosting",
            REGRESSION,
            "Histogram-based regression boosting for larger in-memory datasets.",
            "in_memory",
            "large",
            (
                *HIST_PARAMETERS,
                _select(
                    "loss",
                    "Loss",
                    "squared_error",
                    ("squared_error", "absolute_error", "gamma", "poisson", "quantile"),
                ),
            ),
            supports_early_stopping=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "ada_boost_regressor",
            "AdaBoost regressor",
            "Boosting",
            REGRESSION,
            "Adaptive ensemble emphasizing difficult regression observations.",
            "in_memory",
            "medium",
            (
                N_ESTIMATORS,
                LEARNING_RATE,
                _select("loss", "Loss", "linear", ("linear", "square", "exponential")),
            ),
        ),
        AlgorithmSpec(
            "knn_regressor",
            "k-nearest neighbours regressor",
            "Neighbour methods",
            REGRESSION,
            "Instance-based non-linear regressor retaining the complete training matrix.",
            "in_memory",
            "small",
            (
                _int(
                    "n_neighbors",
                    "Number of neighbours",
                    5,
                    1,
                    1000,
                    search={"kind": "int", "low": 3, "high": 51, "step": 2},
                ),
                _select("weights", "Neighbour weighting", "uniform", ("uniform", "distance")),
                _select("p", "Minkowski power", 2, (1, 2)),
            ),
        ),
        AlgorithmSpec(
            "mlp_regressor",
            "Multilayer perceptron regressor",
            "Neural networks",
            REGRESSION,
            "Configurable dense feed-forward neural network for non-linear tabular regression.",
            "in_memory",
            "medium",
            MLP_PARAMETERS,
            supports_early_stopping=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "xgboost_regressor",
            "XGBoost regressor",
            "Modern boosting",
            REGRESSION,
            "Production-grade regularized gradient tree boosting for regression.",
            "in_memory",
            "large",
            EXTERNAL_BOOST_PARAMETERS,
            dependency="XGBoost",
            supports_early_stopping=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "lightgbm_regressor",
            "LightGBM regressor",
            "Modern boosting",
            REGRESSION,
            "Leaf-wise histogram gradient boosting optimized for large tabular regression.",
            "in_memory",
            "large",
            (
                N_ESTIMATORS,
                LEARNING_RATE,
                _int(
                    "num_leaves",
                    "Number of leaves",
                    31,
                    2,
                    4096,
                    search={"kind": "int", "low": 15, "high": 255},
                ),
                MAX_DEPTH,
                *EXTERNAL_BOOST_PARAMETERS[3:],
            ),
            dependency="LightGBM",
            supports_early_stopping=True,
            automl_default=True,
        ),
        AlgorithmSpec(
            "catboost_regressor",
            "CatBoost regressor",
            "Modern boosting",
            REGRESSION,
            "Ordered gradient boosting with robust defaults for tabular regression.",
            "in_memory",
            "large",
            (
                _int(
                    "iterations",
                    "Boosting iterations",
                    500,
                    10,
                    10000,
                    step=10,
                    search={"kind": "int", "low": 200, "high": 1200, "step": 100},
                ),
                LEARNING_RATE,
                _int(
                    "depth",
                    "Tree depth",
                    6,
                    1,
                    16,
                    search={"kind": "int", "low": 4, "high": 10},
                ),
                _float(
                    "l2_leaf_reg",
                    "L2 leaf regularization",
                    3.0,
                    0.0,
                    1000.0,
                    search={"kind": "float", "low": 1e-3, "high": 100.0, "log": True},
                ),
                _float(
                    "random_strength",
                    "Random strength",
                    1.0,
                    0.0,
                    1000.0,
                    search={"kind": "float", "low": 1e-3, "high": 10.0, "log": True},
                ),
            ),
            dependency="CatBoost",
            supports_early_stopping=True,
            automl_default=True,
        ),
    )


ALGORITHM_SPECS = _algorithm_specs()
ALGORITHM_REGISTRY = {spec.id: spec for spec in ALGORITHM_SPECS}


def training_catalog() -> dict[str, Any]:
    return {
        "contract_version": "1.0",
        "algorithm_count": len(ALGORITHM_SPECS),
        "algorithms": [spec.public_dict() for spec in ALGORITHM_SPECS],
        "optimization_modes": [
            {
                "id": "single",
                "label": "Single model",
                "description": "Fit one configured estimator on the full training scope.",
            },
            {
                "id": "grid_search",
                "label": "Grid search",
                "description": "Deterministically evaluate the curated parameter grid.",
            },
            {
                "id": "random_search",
                "label": "Random search",
                "description": "Evaluate a reproducible random subset of the curated search space.",
            },
            {
                "id": "optuna",
                "label": "Optuna",
                "description": "Bayesian hyperparameter optimization with pruning-ready trial history.",
            },
            {
                "id": "automl",
                "label": "AutoML",
                "description": "Jointly choose an algorithm and its hyperparameters under a trial budget.",
            },
        ],
        "metrics": {
            "binary_classification": [
                {"id": "roc_auc", "label": "ROC AUC", "direction": "maximize"},
                {"id": "average_precision", "label": "Average precision", "direction": "maximize"},
                {"id": "f1", "label": "F1", "direction": "maximize"},
                {"id": "accuracy", "label": "Accuracy", "direction": "maximize"},
                {"id": "balanced_accuracy", "label": "Balanced accuracy", "direction": "maximize"},
            ],
            "multiclass_classification": [
                {"id": "f1_macro", "label": "Macro F1", "direction": "maximize"},
                {"id": "accuracy", "label": "Accuracy", "direction": "maximize"},
                {"id": "balanced_accuracy", "label": "Balanced accuracy", "direction": "maximize"},
                {"id": "neg_log_loss", "label": "Negative log loss", "direction": "maximize"},
            ],
            "regression": [
                {"id": "neg_root_mean_squared_error", "label": "Negative RMSE", "direction": "maximize"},
                {"id": "neg_mean_absolute_error", "label": "Negative MAE", "direction": "maximize"},
                {"id": "r2", "label": "R²", "direction": "maximize"},
            ],
        },
    }


def algorithm_spec(algorithm: str) -> AlgorithmSpec:
    try:
        return ALGORITHM_REGISTRY[algorithm]
    except KeyError as exc:
        raise ValueError(f"Unknown training algorithm '{algorithm}'") from exc


def validate_algorithm_parameters(
    algorithm: str,
    problem_type: ProblemType,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    spec = algorithm_spec(algorithm)
    if problem_type not in spec.problem_types:
        raise ValueError(
            f"Algorithm '{algorithm}' does not support problem type '{problem_type}'"
        )
    if not spec.available:
        raise ValueError(
            f"Algorithm '{algorithm}' requires the unavailable {spec.dependency} dependency"
        )
    by_id = {parameter.id: parameter for parameter in spec.parameters}
    unsupported = sorted(set(parameters) - set(by_id))
    if unsupported:
        raise ValueError(
            f"Unsupported training parameters for '{algorithm}': "
            f"{', '.join(unsupported)}"
        )
    normalized = spec.defaults()
    normalized.update(parameters)
    for parameter_id, value in normalized.items():
        parameter = by_id[parameter_id]
        if value is None:
            if not parameter.nullable:
                raise ValueError(f"Parameter '{parameter_id}' cannot be null")
            continue
        if parameter.kind == "boolean" and not isinstance(value, bool):
            raise ValueError(f"Parameter '{parameter_id}' must be a boolean")
        if parameter.kind == "integer":
            if isinstance(value, bool) or int(value) != value:
                raise ValueError(f"Parameter '{parameter_id}' must be an integer")
            normalized[parameter_id] = int(value)
        elif parameter.kind == "number":
            if isinstance(value, bool):
                raise ValueError(f"Parameter '{parameter_id}' must be numeric")
            normalized[parameter_id] = float(value)
        elif parameter.kind == "integer_list":
            if not isinstance(value, (list, tuple)) or not value:
                raise ValueError(
                    f"Parameter '{parameter_id}' must be a non-empty integer list"
                )
            normalized[parameter_id] = tuple(int(item) for item in value)
            if any(item < 1 for item in normalized[parameter_id]):
                raise ValueError(
                    f"Parameter '{parameter_id}' values must be positive"
                )
        elif parameter.kind == "select" and value not in parameter.options:
            raise ValueError(
                f"Parameter '{parameter_id}' must be one of "
                f"{', '.join(str(item) for item in parameter.options)}"
            )
        if isinstance(normalized[parameter_id], (int, float)):
            numeric = float(normalized[parameter_id])
            if parameter.minimum is not None and numeric < parameter.minimum:
                raise ValueError(
                    f"Parameter '{parameter_id}' must be at least {parameter.minimum}"
                )
            if parameter.maximum is not None and numeric > parameter.maximum:
                raise ValueError(
                    f"Parameter '{parameter_id}' must be at most {parameter.maximum}"
                )
    if algorithm == "logistic_regression" and normalized["penalty"] != "elasticnet":
        normalized.pop("l1_ratio", None)
    if algorithm == "lda_classifier":
        solver = normalized["solver"]
        if solver == "svd":
            normalized["shrinkage"] = None
    return normalized


class LabelEncodedClassifier(ClassifierMixin, BaseEstimator):
    """Make external boosters safe for arbitrary string or numeric class labels."""

    def __init__(self, estimator: Any):
        self.estimator = estimator

    def fit(self, x: Any, y: Any, **fit_params: Any) -> "LabelEncodedClassifier":
        self.label_encoder_ = LabelEncoder().fit(y)
        self.classes_ = self.label_encoder_.classes_
        self.estimator.fit(x, self.label_encoder_.transform(y), **fit_params)
        return self

    def predict(self, x: Any) -> Any:
        encoded = self.estimator.predict(x)
        return self.label_encoder_.inverse_transform(encoded.astype(int))

    def predict_proba(self, x: Any) -> Any:
        return self.estimator.predict_proba(x)

    def decision_function(self, x: Any) -> Any:
        return self.estimator.decision_function(x)


def build_estimator(
    algorithm: str,
    problem_type: ProblemType,
    parameters: dict[str, Any],
    *,
    random_seed: int,
    n_jobs: int,
) -> Any:
    values = validate_algorithm_parameters(algorithm, problem_type, parameters)
    if algorithm == "logistic_regression":
        values = dict(values)
        penalty = values.pop("penalty")
        if penalty == "l2":
            values["l1_ratio"] = 0.0
        elif penalty == "l1":
            values["l1_ratio"] = 1.0
        values = {
            **values,
            "solver": (
                "saga"
                if penalty in {"l1", "elasticnet"}
                else "lbfgs"
            ),
        }

    def passive_aggressive_classifier() -> Any:
        configured = dict(values)
        c_value = float(configured.pop("C"))
        return SGDClassifier(
            random_state=random_seed,
            penalty=None,
            learning_rate="pa1",
            eta0=c_value,
            **configured,
        )

    def passive_aggressive_regressor() -> Any:
        configured = dict(values)
        c_value = float(configured.pop("C"))
        return SGDRegressor(
            random_state=random_seed,
            penalty=None,
            learning_rate="pa1",
            eta0=c_value,
            **configured,
        )

    factories: dict[str, Callable[[], Any]] = {
        "dummy_classifier": lambda: DummyClassifier(random_state=random_seed, **values),
        "logistic_regression": lambda: LogisticRegression(
            random_state=random_seed, **values
        ),
        "ridge_classifier": lambda: RidgeClassifier(**values),
        "sgd_classifier": lambda: SGDClassifier(random_state=random_seed, **values),
        "passive_aggressive_classifier": passive_aggressive_classifier,
        "perceptron_classifier": lambda: Perceptron(random_state=random_seed, **values),
        "linear_svc": lambda: LinearSVC(random_state=random_seed, **values),
        "svc_rbf": lambda: SVC(random_state=random_seed, kernel="rbf", **values),
        "svc_poly": lambda: SVC(random_state=random_seed, kernel="poly", **values),
        "nu_svc": lambda: NuSVC(random_state=random_seed, **values),
        "decision_tree_classifier": lambda: DecisionTreeClassifier(
            random_state=random_seed, **values
        ),
        "random_forest_classifier": lambda: RandomForestClassifier(
            random_state=random_seed, n_jobs=n_jobs, **values
        ),
        "extra_trees_classifier": lambda: ExtraTreesClassifier(
            random_state=random_seed, n_jobs=n_jobs, **values
        ),
        "gradient_boosting_classifier": lambda: GradientBoostingClassifier(
            random_state=random_seed, **values
        ),
        "hist_gradient_boosting_classifier": lambda: HistGradientBoostingClassifier(
            random_state=random_seed, **values
        ),
        "ada_boost_classifier": lambda: AdaBoostClassifier(
            random_state=random_seed, **values
        ),
        "knn_classifier": lambda: KNeighborsClassifier(n_jobs=n_jobs, **values),
        "gaussian_nb": lambda: GaussianNB(**values),
        "bernoulli_nb": lambda: BernoulliNB(**values),
        "complement_nb": lambda: ComplementNB(**values),
        "lda_classifier": lambda: LinearDiscriminantAnalysis(**values),
        "qda_classifier": lambda: QuadraticDiscriminantAnalysis(**values),
        "mlp_classifier": lambda: MLPClassifier(random_state=random_seed, **values),
        "dummy_regressor": lambda: DummyRegressor(**values),
        "linear_regression": lambda: LinearRegression(n_jobs=n_jobs, **values),
        "ridge_regression": lambda: Ridge(random_state=random_seed, **values),
        "lasso_regression": lambda: Lasso(random_state=random_seed, **values),
        "elastic_net_regression": lambda: ElasticNet(
            random_state=random_seed, **values
        ),
        "sgd_regressor": lambda: SGDRegressor(random_state=random_seed, **values),
        "passive_aggressive_regressor": passive_aggressive_regressor,
        "huber_regressor": lambda: HuberRegressor(**values),
        "quantile_regressor": lambda: QuantileRegressor(**values),
        "poisson_regressor": lambda: PoissonRegressor(**values),
        "tweedie_regressor": lambda: TweedieRegressor(**values),
        "linear_svr": lambda: LinearSVR(random_state=random_seed, **values),
        "svr_rbf": lambda: SVR(kernel="rbf", **values),
        "svr_poly": lambda: SVR(kernel="poly", **values),
        "nu_svr": lambda: NuSVR(**values),
        "decision_tree_regressor": lambda: DecisionTreeRegressor(
            random_state=random_seed, **values
        ),
        "random_forest_regressor": lambda: RandomForestRegressor(
            random_state=random_seed, n_jobs=n_jobs, **values
        ),
        "extra_trees_regressor": lambda: ExtraTreesRegressor(
            random_state=random_seed, n_jobs=n_jobs, **values
        ),
        "gradient_boosting_regressor": lambda: GradientBoostingRegressor(
            random_state=random_seed, **values
        ),
        "hist_gradient_boosting_regressor": lambda: HistGradientBoostingRegressor(
            random_state=random_seed, **values
        ),
        "ada_boost_regressor": lambda: AdaBoostRegressor(
            random_state=random_seed, **values
        ),
        "knn_regressor": lambda: KNeighborsRegressor(n_jobs=n_jobs, **values),
        "mlp_regressor": lambda: MLPRegressor(random_state=random_seed, **values),
    }
    if algorithm in factories:
        return factories[algorithm]()
    if algorithm.startswith("xgboost_"):
        from xgboost import XGBClassifier, XGBRegressor

        common = {
            **values,
            "random_state": random_seed,
            "n_jobs": n_jobs,
            "tree_method": "hist",
        }
        estimator = (
            XGBClassifier(**common)
            if algorithm.endswith("classifier")
            else XGBRegressor(**common)
        )
        return (
            LabelEncodedClassifier(estimator)
            if algorithm.endswith("classifier")
            else estimator
        )
    if algorithm.startswith("lightgbm_"):
        from lightgbm import LGBMClassifier, LGBMRegressor

        common = {
            **values,
            "random_state": random_seed,
            "n_jobs": n_jobs,
            "verbosity": -1,
        }
        estimator = (
            LGBMClassifier(**common)
            if algorithm.endswith("classifier")
            else LGBMRegressor(**common)
        )
        return (
            LabelEncodedClassifier(estimator)
            if algorithm.endswith("classifier")
            else estimator
        )
    if algorithm.startswith("catboost_"):
        from catboost import CatBoostClassifier, CatBoostRegressor

        common = {
            **values,
            "random_seed": random_seed,
            "thread_count": n_jobs,
            "verbose": False,
            "allow_writing_files": False,
        }
        return (
            CatBoostClassifier(**common)
            if algorithm.endswith("classifier")
            else CatBoostRegressor(**common)
        )
    raise ValueError(f"No estimator factory is registered for '{algorithm}'")


def curated_search_space(algorithm: str) -> dict[str, dict[str, Any]]:
    return {
        parameter.id: dict(parameter.search)
        for parameter in algorithm_spec(algorithm).parameters
        if parameter.search
    }


def automl_algorithms(problem_type: ProblemType) -> list[str]:
    return [
        spec.id
        for spec in ALGORITHM_SPECS
        if problem_type in spec.problem_types
        and spec.automl_default
        and spec.available
    ]
