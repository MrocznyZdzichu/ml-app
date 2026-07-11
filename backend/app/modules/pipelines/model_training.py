from __future__ import annotations

import math
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal

import numpy as np
from sklearn.base import clone
from sklearn.metrics import get_scorer
from sklearn.model_selection import (
    KFold,
    PredefinedSplit,
    StratifiedKFold,
    cross_val_score,
)

from app.modules.pipelines.modeling_catalog import (
    ProblemType,
    algorithm_spec,
    automl_algorithms,
    build_estimator,
    curated_search_space,
    parameter_is_active,
    validate_algorithm_parameters,
)
from app.modules.pipelines.domain import PipelineExecutionCancelled
from app.modules.pipelines.runtime import json_safe

OptimizationMode = Literal[
    "single",
    "grid_search",
    "random_search",
    "optuna",
    "automl",
]
ValidationStrategy = Literal["auto", "holdout", "cross_validation"]


@dataclass(frozen=True)
class TrainingFitResult:
    estimator: Any
    algorithm: str
    parameters: dict[str, Any]
    processed_row_count: int
    optimization_summary: dict[str, Any]


def default_metric(problem_type: ProblemType) -> str:
    if problem_type == "binary_classification":
        return "roc_auc"
    if problem_type == "multiclass_classification":
        return "f1_macro"
    return "neg_root_mean_squared_error"


class ModelOptimizationEngine:
    """Resource-bounded model selection over an explicitly materialized full relation."""

    def fit(
        self,
        *,
        algorithm: str,
        problem_type: ProblemType,
        parameters: dict[str, Any],
        random_seed: int,
        epochs: int,
        x_train: np.ndarray,
        y_train: np.ndarray,
        x_validation: np.ndarray | None,
        y_validation: np.ndarray | None,
        mode: OptimizationMode,
        validation_strategy: ValidationStrategy,
        primary_metric: str,
        cv_folds: int,
        max_trials: int,
        timeout_seconds: int,
        max_parallel_jobs: int,
        candidate_algorithms: list[str],
        search_space: dict[str, dict[str, Any]] | None = None,
        cv_fold_assignments: np.ndarray | None = None,
        cv_strategy: str = "",
        emit_event: Callable[[str, dict[str, Any]], None] | None = None,
        is_cancel_requested: Callable[[], bool] | None = None,
    ) -> TrainingFitResult:
        metric = (
            default_metric(problem_type)
            if primary_metric in {"", "auto"}
            else primary_metric
        )
        resolved_validation = self._validation_strategy(
            validation_strategy,
            x_validation,
            y_validation,
        )
        resolved_cv_folds = (
            len(np.unique(cv_fold_assignments))
            if cv_fold_assignments is not None
            else cv_folds
        )
        if mode == "single":
            estimator = self._build(
                algorithm,
                problem_type,
                parameters,
                random_seed,
                max_parallel_jobs,
                epochs,
            )
            estimator.fit(x_train, y_train)
            return TrainingFitResult(
                estimator=estimator,
                algorithm=algorithm,
                parameters=validate_algorithm_parameters(
                    algorithm, problem_type, parameters
                ),
                processed_row_count=len(y_train),
                optimization_summary={
                    "mode": "single",
                    "random_seed": random_seed,
                    "primary_metric": metric,
                    "validation_strategy": resolved_validation,
                    "trial_count": 1,
                    "successful_trial_count": 1,
                    "failed_trial_count": 0,
                    "best_score": None,
                    "best_algorithm": algorithm,
                    "best_parameters": validate_algorithm_parameters(
                        algorithm, problem_type, parameters
                    ),
                    "trials": [],
                    "cv_fold_source": (
                        "upstream_plan"
                        if cv_fold_assignments is not None
                        else "generated"
                    ),
                },
            )
        if mode in {"grid_search", "random_search"}:
            return self._fit_enumerated(
                algorithm=algorithm,
                problem_type=problem_type,
                base_parameters=parameters,
                random_seed=random_seed,
                epochs=epochs,
                x_train=x_train,
                y_train=y_train,
                x_validation=x_validation,
                y_validation=y_validation,
                mode=mode,
                validation_strategy=resolved_validation,
                metric=metric,
                cv_folds=resolved_cv_folds,
                max_trials=max_trials,
                timeout_seconds=timeout_seconds,
                max_parallel_jobs=max_parallel_jobs,
                search_space=search_space or {},
                cv_fold_assignments=cv_fold_assignments,
                cv_strategy=cv_strategy,
                emit_event=emit_event,
                is_cancel_requested=is_cancel_requested,
            )
        return self._fit_optuna(
            algorithm=algorithm,
            problem_type=problem_type,
            base_parameters=parameters,
            random_seed=random_seed,
            epochs=epochs,
            x_train=x_train,
            y_train=y_train,
            x_validation=x_validation,
            y_validation=y_validation,
            mode=mode,
            validation_strategy=resolved_validation,
            metric=metric,
            cv_folds=resolved_cv_folds,
            max_trials=max_trials,
            timeout_seconds=timeout_seconds,
            max_parallel_jobs=max_parallel_jobs,
            candidate_algorithms=candidate_algorithms,
            search_space=search_space or {},
            cv_fold_assignments=cv_fold_assignments,
            cv_strategy=cv_strategy,
            emit_event=emit_event,
            is_cancel_requested=is_cancel_requested,
        )

    def _fit_enumerated(
        self,
        *,
        algorithm: str,
        problem_type: ProblemType,
        base_parameters: dict[str, Any],
        random_seed: int,
        epochs: int,
        x_train: np.ndarray,
        y_train: np.ndarray,
        x_validation: np.ndarray | None,
        y_validation: np.ndarray | None,
        mode: Literal["grid_search", "random_search"],
        validation_strategy: Literal["holdout", "cross_validation"],
        metric: str,
        cv_folds: int,
        max_trials: int,
        timeout_seconds: int,
        max_parallel_jobs: int,
        search_space: dict[str, dict[str, Any]],
        cv_fold_assignments: np.ndarray | None,
        cv_strategy: str,
        emit_event: Callable[[str, dict[str, Any]], None] | None,
        is_cancel_requested: Callable[[], bool] | None,
    ) -> TrainingFitResult:
        raw_space = self._resolved_search_space(algorithm, search_space)
        space = {
            key: self._discrete_values(value)
            for key, value in raw_space.items()
        }
        if not space:
            raise ValueError(
                f"Algorithm '{algorithm}' has no curated hyperparameter search space"
            )
        total_candidate_count = self._conditional_candidate_count(
            algorithm,
            space,
            base_parameters,
        )
        if mode == "grid_search":
            candidates = list(
                self._iter_conditional_candidates(
                    algorithm,
                    space,
                    base_parameters,
                    limit=max_trials,
                )
            )
        else:
            sample_size = min(max_trials, total_candidate_count)
            indices = sorted(random.Random(random_seed).sample(range(total_candidate_count), sample_size))
            candidates = [
                self._conditional_candidate_at(
                    algorithm,
                    space,
                    base_parameters,
                    index,
                )
                for index in indices
            ]
        started = time.monotonic()
        if emit_event:
            emit_event(
                "optimization.started",
                {
                    "message": f"{mode.replace('_', ' ').title()} started",
                    "mode": mode,
                    "algorithm": algorithm,
                    "metric": metric,
                    "validation_strategy": validation_strategy,
                    "planned_trial_count": len(candidates),
                    "total_candidate_count": total_candidate_count,
                    "max_trials": max_trials,
                    "timeout_seconds": timeout_seconds,
                },
            )
        trials: list[dict[str, Any]] = []
        best: tuple[float, dict[str, Any]] | None = None
        for index, candidate in enumerate(candidates):
            if is_cancel_requested and is_cancel_requested():
                raise PipelineExecutionCancelled("Pipeline run was cancelled")
            if time.monotonic() - started >= timeout_seconds:
                break
            merged = {**base_parameters, **candidate}
            trial_started_at = datetime.now(timezone.utc)
            if emit_event:
                emit_event(
                    "optimization.trial_started",
                    {
                        "message": f"Trial {index + 1} of {len(candidates)} started",
                        "trial_number": index,
                        "trial_index": index + 1,
                        "planned_trial_count": len(candidates),
                        "algorithm": algorithm,
                        "parameters": json_safe(merged),
                        "started_at": trial_started_at.isoformat(),
                    },
                )
            try:
                estimator = self._build(
                    algorithm,
                    problem_type,
                    merged,
                    random_seed + index,
                    max_parallel_jobs,
                    epochs,
                )
                score, fold_scores = self._score(
                    estimator,
                    problem_type=problem_type,
                    metric=metric,
                    validation_strategy=validation_strategy,
                    cv_folds=cv_folds,
                    random_seed=random_seed,
                    x_train=x_train,
                    y_train=y_train,
                    x_validation=x_validation,
                    y_validation=y_validation,
                    cv_fold_assignments=cv_fold_assignments,
                    cv_strategy=cv_strategy,
                )
                normalized = validate_algorithm_parameters(
                    algorithm, problem_type, merged
                )
                trials.append({
                    "number": index,
                    "status": "succeeded",
                    "algorithm": algorithm,
                    "score": score,
                    "fold_scores": fold_scores,
                    "parameters": normalized,
                })
                if emit_event:
                    emit_event(
                        "optimization.trial_succeeded",
                        {
                            "message": f"Trial {index + 1} succeeded",
                            "trial_number": index,
                            "trial_index": index + 1,
                            "planned_trial_count": len(candidates),
                            "algorithm": algorithm,
                            "score": score,
                            "fold_scores": fold_scores,
                            "parameters": json_safe(normalized),
                            "elapsed_seconds": round(
                                (
                                    datetime.now(timezone.utc) - trial_started_at
                                ).total_seconds(),
                                6,
                            ),
                        },
                    )
                if best is None or score > best[0]:
                    best = (score, normalized)
                    if emit_event:
                        emit_event(
                            "optimization.best_updated",
                            {
                                "message": "Best trial updated",
                                "trial_number": index,
                                "score": score,
                                "algorithm": algorithm,
                                "parameters": json_safe(normalized),
                            },
                        )
            except Exception as exc:
                trials.append({
                    "number": index,
                    "status": "failed",
                    "algorithm": algorithm,
                    "score": None,
                    "fold_scores": [],
                    "parameters": merged,
                    "error": str(exc)[:1000],
                })
                if emit_event:
                    emit_event(
                        "optimization.trial_failed",
                        {
                            "message": f"Trial {index + 1} failed",
                            "trial_number": index,
                            "trial_index": index + 1,
                            "planned_trial_count": len(candidates),
                            "algorithm": algorithm,
                            "parameters": json_safe(merged),
                            "error": str(exc)[:1000],
                            "elapsed_seconds": round(
                                (
                                    datetime.now(timezone.utc) - trial_started_at
                                ).total_seconds(),
                                6,
                            ),
                        },
                    )
        if best is None:
            messages = [
                str(item.get("error"))
                for item in trials
                if item.get("error")
            ]
            detail = f": {messages[0]}" if messages else ""
            raise ValueError(f"Every hyperparameter trial failed{detail}")
        estimator = self._build(
            algorithm,
            problem_type,
            best[1],
            random_seed,
            max_parallel_jobs,
            epochs,
        )
        estimator.fit(x_train, y_train)
        if emit_event:
            emit_event(
                "optimization.refit_completed",
                {
                    "message": "Best model refit on full training data",
                    "algorithm": algorithm,
                    "parameters": json_safe(best[1]),
                    "training_row_count": len(y_train),
                },
            )
        processed = self._processed_rows(
            len(y_train),
            len(trials),
            cv_folds,
            validation_strategy,
            cv_fold_assignments,
            cv_strategy,
        )
        return TrainingFitResult(
            estimator=estimator,
            algorithm=algorithm,
            parameters=best[1],
            processed_row_count=processed,
            optimization_summary=self._summary(
                mode=mode,
                metric=metric,
                random_seed=random_seed,
                validation_strategy=validation_strategy,
                best_score=best[0],
                best_algorithm=algorithm,
                best_parameters=best[1],
                search_space={key: list(values) for key, values in space.items()},
                planned_trial_count=len(candidates),
                total_candidate_count=total_candidate_count,
                max_trials=max_trials,
                trials=trials,
                started=started,
                timeout_seconds=timeout_seconds,
                cv_fold_source=(
                    "upstream_plan"
                    if cv_fold_assignments is not None
                    else "generated"
                ),
            ),
        )

    def _fit_optuna(
        self,
        *,
        algorithm: str,
        problem_type: ProblemType,
        base_parameters: dict[str, Any],
        random_seed: int,
        epochs: int,
        x_train: np.ndarray,
        y_train: np.ndarray,
        x_validation: np.ndarray | None,
        y_validation: np.ndarray | None,
        mode: Literal["optuna", "automl"],
        validation_strategy: Literal["holdout", "cross_validation"],
        metric: str,
        cv_folds: int,
        max_trials: int,
        timeout_seconds: int,
        max_parallel_jobs: int,
        candidate_algorithms: list[str],
        search_space: dict[str, dict[str, Any]],
        cv_fold_assignments: np.ndarray | None,
        cv_strategy: str,
        emit_event: Callable[[str, dict[str, Any]], None] | None,
        is_cancel_requested: Callable[[], bool] | None,
    ) -> TrainingFitResult:
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        if mode == "automl":
            candidates = candidate_algorithms or automl_algorithms(problem_type)
            candidates = list(dict.fromkeys(candidates))
            for candidate in candidates:
                spec = algorithm_spec(candidate)
                if problem_type not in spec.problem_types:
                    raise ValueError(
                        f"AutoML candidate '{candidate}' does not support {problem_type}"
                    )
                if not spec.available:
                    raise ValueError(
                        f"AutoML candidate '{candidate}' requires unavailable "
                        f"{spec.dependency}"
                    )
            if not candidates:
                raise ValueError("AutoML requires at least one available candidate algorithm")
        else:
            candidates = [algorithm]
        sampler = optuna.samplers.TPESampler(seed=random_seed)
        study = optuna.create_study(direction="maximize", sampler=sampler)

        def objective(trial: Any) -> float:
            selected = (
                trial.suggest_categorical("algorithm", candidates)
                if mode == "automl"
                else algorithm
            )
            base = base_parameters if selected == algorithm else {}
            suggested = self._suggest_parameters(
                trial,
                selected,
                search_space=search_space,
                base_parameters=base,
                prefix=f"{selected}__" if mode == "automl" else "",
                allow_unscoped_overrides=mode != "automl",
            )
            merged = {**base, **suggested}
            trial.set_user_attr("algorithm", selected)
            trial.set_user_attr("parameters", merged)
            estimator = self._build(
                selected,
                problem_type,
                merged,
                random_seed + trial.number,
                max_parallel_jobs,
                epochs,
            )
            score, fold_scores = self._score(
                estimator,
                problem_type=problem_type,
                metric=metric,
                validation_strategy=validation_strategy,
                cv_folds=cv_folds,
                random_seed=random_seed,
                x_train=x_train,
                y_train=y_train,
                x_validation=x_validation,
                y_validation=y_validation,
                cv_fold_assignments=cv_fold_assignments,
                cv_strategy=cv_strategy,
            )
            trial.set_user_attr("fold_scores", fold_scores)
            return score

        started = time.monotonic()
        if emit_event:
            emit_event(
                "optimization.started",
                {
                    "message": f"{mode.replace('_', ' ').title()} started",
                    "mode": mode,
                    "algorithm": algorithm,
                    "metric": metric,
                    "validation_strategy": validation_strategy,
                    "planned_trial_count": max_trials,
                    "total_candidate_count": max_trials,
                    "max_trials": max_trials,
                    "timeout_seconds": timeout_seconds,
                    "candidate_algorithms": candidates,
                },
            )

        def callback(study: Any, trial: Any) -> None:
            selected = str(trial.user_attrs.get("algorithm") or algorithm)
            raw_parameters = trial.user_attrs.get("parameters") or {}
            state = str(trial.state.name).lower()
            event_type = (
                "optimization.trial_succeeded"
                if state == "complete"
                else "optimization.trial_failed"
            )
            if emit_event:
                emit_event(
                    event_type,
                    {
                        "message": (
                            f"Trial {trial.number + 1} succeeded"
                            if state == "complete"
                            else f"Trial {trial.number + 1} ended as {state}"
                        ),
                        "trial_number": trial.number,
                        "trial_index": trial.number + 1,
                        "planned_trial_count": max_trials,
                        "algorithm": selected,
                        "score": float(trial.value) if trial.value is not None else None,
                        "fold_scores": trial.user_attrs.get("fold_scores") or [],
                        "parameters": json_safe(raw_parameters),
                        "state": state,
                    },
                )
            if is_cancel_requested and is_cancel_requested():
                study.stop()

        study.optimize(
            objective,
            n_trials=max_trials,
            timeout=timeout_seconds,
            n_jobs=1,
            catch=(Exception,),
            show_progress_bar=False,
            callbacks=[callback],
        )
        trials = []
        for item in study.trials:
            state = str(item.state.name).lower()
            selected = str(item.user_attrs.get("algorithm") or algorithm)
            raw_parameters = item.user_attrs.get("parameters") or {}
            trials.append({
                "number": item.number,
                "status": "succeeded" if state == "complete" else state,
                "algorithm": selected,
                "score": float(item.value) if item.value is not None else None,
                "fold_scores": item.user_attrs.get("fold_scores") or [],
                "parameters": raw_parameters,
                **(
                    {"error": "Trial failed; inspect worker logs for estimator details"}
                    if state == "fail"
                    else {}
                ),
            })
        completed = [
            item for item in study.trials if item.value is not None
        ]
        if not completed:
            raise ValueError("Every Optuna trial failed")
        best_trial = study.best_trial
        best_algorithm = str(best_trial.user_attrs.get("algorithm") or algorithm)
        best_parameters = validate_algorithm_parameters(
            best_algorithm,
            problem_type,
            dict(best_trial.user_attrs.get("parameters") or {}),
        )
        estimator = self._build(
            best_algorithm,
            problem_type,
            best_parameters,
            random_seed,
            max_parallel_jobs,
            epochs,
        )
        estimator.fit(x_train, y_train)
        if emit_event:
            emit_event(
                "optimization.refit_completed",
                {
                    "message": "Best model refit on full training data",
                    "algorithm": best_algorithm,
                    "parameters": json_safe(best_parameters),
                    "training_row_count": len(y_train),
                },
            )
        processed = self._processed_rows(
            len(y_train),
            len(study.trials),
            cv_folds,
            validation_strategy,
            cv_fold_assignments,
            cv_strategy,
        )
        return TrainingFitResult(
            estimator=estimator,
            algorithm=best_algorithm,
            parameters=best_parameters,
            processed_row_count=processed,
            optimization_summary=self._summary(
                mode=mode,
                metric=metric,
                random_seed=random_seed,
                validation_strategy=validation_strategy,
                best_score=float(study.best_value),
                best_algorithm=best_algorithm,
                best_parameters=best_parameters,
                search_space={
                    candidate: self._resolved_search_space(candidate, search_space)
                    for candidate in candidates
                },
                planned_trial_count=max_trials,
                total_candidate_count=max_trials,
                max_trials=max_trials,
                trials=trials,
                started=started,
                timeout_seconds=timeout_seconds,
                cv_fold_source=(
                    "upstream_plan"
                    if cv_fold_assignments is not None
                    else "generated"
                ),
            ),
        )

    @staticmethod
    def _validation_strategy(
        requested: ValidationStrategy,
        x_validation: np.ndarray | None,
        y_validation: np.ndarray | None,
    ) -> Literal["holdout", "cross_validation"]:
        has_validation = x_validation is not None and y_validation is not None
        if requested == "holdout" and not has_validation:
            raise ValueError(
                "Holdout optimization requires an explicit validation input"
            )
        if requested == "auto":
            return "holdout" if has_validation else "cross_validation"
        return requested

    @staticmethod
    def _build(
        algorithm: str,
        problem_type: ProblemType,
        parameters: dict[str, Any],
        random_seed: int,
        max_parallel_jobs: int,
        epochs: int,
    ) -> Any:
        estimator = build_estimator(
            algorithm,
            problem_type,
            parameters,
            random_seed=random_seed,
            n_jobs=max_parallel_jobs,
        )
        if algorithm_spec(algorithm).execution_mode == "incremental":
            available = estimator.get_params(deep=False)
            patch: dict[str, Any] = {}
            if "max_iter" in available:
                patch["max_iter"] = epochs
            if "tol" in available:
                patch["tol"] = None
            if patch:
                estimator.set_params(**patch)
        return estimator

    @staticmethod
    def _score(
        estimator: Any,
        *,
        problem_type: ProblemType,
        metric: str,
        validation_strategy: Literal["holdout", "cross_validation"],
        cv_folds: int,
        random_seed: int,
        x_train: np.ndarray,
        y_train: np.ndarray,
        x_validation: np.ndarray | None,
        y_validation: np.ndarray | None,
        cv_fold_assignments: np.ndarray | None,
        cv_strategy: str,
    ) -> tuple[float, list[float]]:
        scorer = get_scorer(metric)
        if validation_strategy == "holdout":
            if x_validation is None or y_validation is None:
                raise ValueError("Holdout validation input is missing")
            fitted = clone(estimator).fit(x_train, y_train)
            score = float(scorer(fitted, x_validation, y_validation))
            return score, [score]
        if cv_fold_assignments is not None:
            if len(cv_fold_assignments) != len(y_train):
                raise ValueError(
                    "Upstream CV fold assignments do not match the training row count"
                )
            splitter: Any = (
                ModelOptimizationEngine._time_series_splits(cv_fold_assignments)
                if cv_strategy == "time"
                else PredefinedSplit(cv_fold_assignments.astype(int))
            )
        else:
            splitter = (
                StratifiedKFold(
                    n_splits=cv_folds,
                    shuffle=True,
                    random_state=random_seed,
                )
                if problem_type != "regression"
                else KFold(
                    n_splits=cv_folds,
                    shuffle=True,
                    random_state=random_seed,
                )
            )
        scores = cross_val_score(
            estimator,
            x_train,
            y_train,
            scoring=metric,
            cv=splitter,
            n_jobs=1,
            error_score="raise",
        )
        return float(np.mean(scores)), [float(value) for value in scores]

    @staticmethod
    def _ordered_search_parameter_ids(
        algorithm: str,
        space: dict[str, dict[str, Any]],
    ) -> list[str]:
        parameters = {parameter.id: parameter for parameter in algorithm_spec(algorithm).parameters}
        ordered: list[str] = []
        visiting: set[str] = set()

        def visit(parameter_id: str) -> None:
            if parameter_id in ordered:
                return
            if parameter_id in visiting:
                raise ValueError(
                    f"Conditional search parameters for '{algorithm}' contain a cycle"
                )
            visiting.add(parameter_id)
            parameter = parameters[parameter_id]
            for controller in (parameter.active_when or {}):
                if controller in space:
                    visit(controller)
            visiting.remove(parameter_id)
            ordered.append(parameter_id)

        for parameter_id in space:
            visit(parameter_id)
        return ordered

    @classmethod
    def _conditional_candidate_counter(
        cls,
        algorithm: str,
        space: dict[str, list[Any]],
        base_parameters: dict[str, Any],
    ) -> tuple[list[str], dict[str, Any], tuple[str, ...], Callable[[int, tuple[tuple[str, Any], ...]], int]]:
        spec = algorithm_spec(algorithm)
        parameters = {parameter.id: parameter for parameter in spec.parameters}
        ordered = cls._ordered_search_parameter_ids(algorithm, space)
        base_values = spec.defaults()
        base_values.update(base_parameters)
        controller_ids = tuple(sorted({
            controller
            for parameter_id in ordered
            for controller in (parameters[parameter_id].active_when or {})
            if controller in space
        }))
        cache: dict[tuple[int, tuple[tuple[str, Any], ...]], int] = {}

        def count(index: int, selected: tuple[tuple[str, Any], ...]) -> int:
            key = (index, selected)
            if key in cache:
                return cache[key]
            if index == len(ordered):
                return 1
            parameter_id = ordered[index]
            context = {**base_values, **dict(selected)}
            parameter = parameters[parameter_id]
            if not parameter_is_active(parameter, context):
                result = count(index + 1, selected)
            elif parameter_id not in controller_ids:
                result = len(space[parameter_id]) * count(index + 1, selected)
            else:
                result = sum(
                    count(
                        index + 1,
                        tuple(
                            (controller, value if controller == parameter_id else context[controller])
                            for controller in controller_ids
                            if controller == parameter_id or controller in context
                        ),
                    )
                    for value in space[parameter_id]
                )
            cache[key] = result
            return result

        return ordered, base_values, controller_ids, count

    @classmethod
    def _conditional_candidate_count(
        cls,
        algorithm: str,
        space: dict[str, list[Any]],
        base_parameters: dict[str, Any],
    ) -> int:
        _, _, _, count = cls._conditional_candidate_counter(algorithm, space, base_parameters)
        return count(0, ())

    @classmethod
    def _iter_conditional_candidates(
        cls,
        algorithm: str,
        space: dict[str, list[Any]],
        base_parameters: dict[str, Any],
        *,
        limit: int,
    ) -> Any:
        spec = algorithm_spec(algorithm)
        parameters = {parameter.id: parameter for parameter in spec.parameters}
        ordered = cls._ordered_search_parameter_ids(algorithm, space)
        context = spec.defaults()
        context.update(base_parameters)
        emitted = 0

        def visit(index: int, selected: dict[str, Any], values: dict[str, Any]) -> Any:
            nonlocal emitted
            if emitted >= limit:
                return
            if index == len(ordered):
                emitted += 1
                yield dict(selected)
                return
            parameter_id = ordered[index]
            parameter = parameters[parameter_id]
            if not parameter_is_active(parameter, values):
                yield from visit(index + 1, selected, values)
                return
            for value in space[parameter_id]:
                if emitted >= limit:
                    return
                next_selected = {**selected, parameter_id: value}
                yield from visit(index + 1, next_selected, {**values, parameter_id: value})

        yield from visit(0, {}, context)

    @classmethod
    def _conditional_candidate_at(
        cls,
        algorithm: str,
        space: dict[str, list[Any]],
        base_parameters: dict[str, Any],
        target: int,
    ) -> dict[str, Any]:
        spec = algorithm_spec(algorithm)
        parameters = {parameter.id: parameter for parameter in spec.parameters}
        ordered, base_values, controller_ids, count = cls._conditional_candidate_counter(
            algorithm,
            space,
            base_parameters,
        )
        selected: dict[str, Any] = {}
        values = dict(base_values)
        for index, parameter_id in enumerate(ordered):
            parameter = parameters[parameter_id]
            if not parameter_is_active(parameter, values):
                continue
            for value in space[parameter_id]:
                next_values = {**values, parameter_id: value}
                next_selected = {**selected, parameter_id: value}
                controller_state = tuple(
                    (controller, next_values[controller])
                    for controller in controller_ids
                    if controller in next_values
                )
                branch_size = count(index + 1, controller_state)
                if target < branch_size:
                    selected = next_selected
                    values = next_values
                    break
                target -= branch_size
            else:
                raise ValueError("Conditional candidate index is outside the search space")
        return selected

    @staticmethod
    def _discrete_values(space: dict[str, Any]) -> list[Any]:
        if space["kind"] == "categorical":
            return [
                None if isinstance(value, str) and value.strip().lower() in {"none", "null"} else value
                for value in space["values"]
            ]
        low = space["low"]
        high = space["high"]
        points = int(space.get("points") or 0)
        if points >= 1:
            if space.get("log") and float(low) > 0 and float(high) > 0:
                values = np.geomspace(float(low), float(high), num=points)
            else:
                values = np.linspace(float(low), float(high), num=points)
            if space["kind"] == "int":
                result = list(dict.fromkeys(int(round(value)) for value in values))
            else:
                result = list(dict.fromkeys(float(value) for value in values))
            return [*result, *([None] if space.get("include_null") else [])]
        if space["kind"] == "int":
            step = int(space.get("step") or max(1, round((high - low) / 2)))
            middle = int(low + ((high - low) // (2 * step)) * step)
            result = list(dict.fromkeys([int(low), middle, int(high)]))
            return [*result, *([None] if space.get("include_null") else [])]
        if space.get("log") and low > 0:
            middle = math.sqrt(float(low) * float(high))
        else:
            middle = (float(low) + float(high)) / 2
        result = list(dict.fromkeys([float(low), middle, float(high)]))
        return [*result, *([None] if space.get("include_null") else [])]

    @staticmethod
    def _resolved_search_space(
        algorithm: str,
        overrides: dict[str, dict[str, Any]],
        *,
        allow_unscoped_overrides: bool = True,
    ) -> dict[str, dict[str, Any]]:
        spec = algorithm_spec(algorithm)
        parameters = {parameter.id: parameter for parameter in spec.parameters}
        curated = curated_search_space(algorithm)
        resolved = {key: dict(value) for key, value in curated.items()}
        allowed = set(curated)
        scoped_prefix = f"{algorithm}__"
        for key, value in overrides.items():
            if key.startswith(scoped_prefix):
                parameter_id = key.removeprefix(scoped_prefix)
            elif allow_unscoped_overrides:
                parameter_id = key
            else:
                continue
            if parameter_id in allowed:
                resolved[parameter_id] = ModelOptimizationEngine._normalized_search_space(
                    parameters[parameter_id],
                    value,
                )
        return resolved

    @staticmethod
    def _normalized_search_space(parameter: Any, space: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(space)
        if normalized.get("kind") != "categorical" or not isinstance(normalized.get("values"), list):
            return normalized
        values = [
            ModelOptimizationEngine._normalize_categorical_search_value(value)
            for value in normalized["values"]
        ]
        if parameter.kind == "select" and parameter.options:
            values = [
                value
                for value in values
                if value in parameter.options and not (
                    value is None and not parameter.nullable
                )
            ]
        deduplicated = []
        for value in values:
            if not any(value == existing for existing in deduplicated):
                deduplicated.append(value)
        values = deduplicated
        if not values:
            raise ValueError(
                f"Search space for parameter '{parameter.id}' has no supported values"
            )
        normalized["values"] = values
        return normalized

    @staticmethod
    def _normalize_categorical_search_value(value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return "__mlapp_unsupported_empty__"
            if stripped.lower() in {"none", "null"}:
                return None
            return stripped
        return value

    @staticmethod
    def _suggest_parameters(
        trial: Any,
        algorithm: str,
        *,
        search_space: dict[str, dict[str, Any]],
        base_parameters: dict[str, Any],
        prefix: str,
        allow_unscoped_overrides: bool = True,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}
        spec = algorithm_spec(algorithm)
        parameters = {parameter.id: parameter for parameter in spec.parameters}
        resolved = ModelOptimizationEngine._resolved_search_space(
            algorithm,
            search_space,
            allow_unscoped_overrides=allow_unscoped_overrides,
        )
        context = spec.defaults()
        context.update(base_parameters)
        for parameter_id in ModelOptimizationEngine._ordered_search_parameter_ids(
            algorithm,
            resolved,
        ):
            parameter = parameters[parameter_id]
            if not parameter_is_active(parameter, context):
                continue
            space = resolved[parameter_id]
            name = f"{prefix}{parameter_id}"
            if space["kind"] == "categorical":
                candidates = list(space["values"])
                encoded = []
                decoded: dict[Any, Any] = {}
                for index, item in enumerate(candidates):
                    if item is None:
                        value = "__mlapp_null__"
                    elif isinstance(item, (list, tuple, dict)):
                        value = (
                            f"__mlapp_json_{index}__"
                            f"{json.dumps(item, sort_keys=True)}"
                        )
                    else:
                        value = item
                    encoded.append(value)
                    decoded[value] = item
                selected = trial.suggest_categorical(name, encoded)
                values[parameter_id] = decoded[selected]
            else:
                use_none = bool(space.get("include_null")) and trial.suggest_categorical(
                    f"{name}__mode",
                    ["value", "none"],
                ) == "none"
                if use_none:
                    values[parameter_id] = None
                elif space["kind"] == "int":
                    step = space.get("step")
                    if step is None:
                        step = 1
                        if space.get("points") and not space.get("log", False):
                            low = int(space["low"])
                            high = int(space["high"])
                            points = max(2, int(space["points"]))
                            step = max(1, round((high - low) / max(1, points - 1)))
                    values[parameter_id] = trial.suggest_int(
                        name,
                        int(space["low"]),
                        int(space["high"]),
                        step=int(step),
                        log=bool(space.get("log", False)),
                    )
                else:
                    values[parameter_id] = trial.suggest_float(
                        name,
                        float(space["low"]),
                        float(space["high"]),
                        step=space.get("step"),
                        log=bool(space.get("log", False)),
                    )
            context[parameter_id] = values[parameter_id]
        return values

    @staticmethod
    def _processed_rows(
        row_count: int,
        trial_count: int,
        cv_folds: int,
        validation_strategy: Literal["holdout", "cross_validation"],
        cv_fold_assignments: np.ndarray | None,
        cv_strategy: str,
    ) -> int:
        if validation_strategy == "holdout":
            optimization_rows = row_count * trial_count
        elif cv_fold_assignments is not None and cv_strategy == "time":
            folds = sorted(int(value) for value in np.unique(cv_fold_assignments))
            per_trial = sum(
                int(np.sum(cv_fold_assignments < fold))
                for fold in folds[1:]
            )
            optimization_rows = per_trial * trial_count
        else:
            optimization_rows = (
                row_count * max(1, cv_folds - 1) * trial_count
            )
        return row_count + optimization_rows

    @staticmethod
    def _summary(
        *,
        mode: str,
        metric: str,
        random_seed: int,
        validation_strategy: str,
        best_score: float,
        best_algorithm: str,
        best_parameters: dict[str, Any],
        search_space: dict[str, Any],
        planned_trial_count: int,
        total_candidate_count: int,
        max_trials: int,
        trials: list[dict[str, Any]],
        started: float,
        timeout_seconds: int,
        cv_fold_source: str,
    ) -> dict[str, Any]:
        succeeded = sum(item["status"] == "succeeded" for item in trials)
        return {
            "mode": mode,
            "random_seed": random_seed,
            "primary_metric": metric,
            "validation_strategy": validation_strategy,
            "trial_count": len(trials),
            "planned_trial_count": planned_trial_count,
            "total_candidate_count": total_candidate_count,
            "max_trials": max_trials,
            "successful_trial_count": succeeded,
            "failed_trial_count": len(trials) - succeeded,
            "best_score": best_score,
            "best_algorithm": best_algorithm,
            "best_parameters": best_parameters,
            "search_space": search_space,
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "timeout_seconds": timeout_seconds,
            "timed_out": (
                time.monotonic() - started >= timeout_seconds
                and len(trials) > 0
            ),
            "stopped_by_max_trials": (
                len(trials) >= max_trials
                and total_candidate_count > len(trials)
            ),
            "trials": trials[:1000],
            "trial_history_truncated": len(trials) > 1000,
            "cv_fold_source": cv_fold_source,
        }

    @staticmethod
    def _time_series_splits(assignments: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
        folds = sorted(int(value) for value in np.unique(assignments))
        splits = [
            (
                np.flatnonzero(assignments < fold),
                np.flatnonzero(assignments == fold),
            )
            for fold in folds[1:]
        ]
        if not splits or any(not len(train) or not len(test) for train, test in splits):
            raise ValueError(
                "Ordered time-series CV requires at least two non-empty chronological folds"
            )
        return splits
