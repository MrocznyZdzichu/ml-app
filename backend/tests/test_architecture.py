"""Executable dependency rules for the modular backend."""

from __future__ import annotations

import ast
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_application_modules_depend_on_task_queue_port_not_worker_adapter() -> None:
    offenders = {
        str(path.relative_to(APP_ROOT)): sorted(
            module for module in _imports(path) if module.startswith("app.worker")
        )
        for path in (APP_ROOT / "modules").rglob("*.py")
        if any(module.startswith("app.worker") for module in _imports(path))
    }
    assert offenders == {}


def test_routers_resolve_services_from_composition_root() -> None:
    offenders: list[str] = []
    for path in (APP_ROOT / "modules").rglob("router.py"):
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id.endswith("Service"):
                offenders.append(f"{path.relative_to(APP_ROOT)}:{node.lineno}:{node.func.id}")
    assert offenders == []


def test_principal_identity_has_no_http_framework_dependency() -> None:
    imports = _imports(APP_ROOT / "core" / "identity.py")
    assert not any(module.startswith("fastapi") for module in imports)


def test_migrated_application_services_have_no_http_framework_dependency() -> None:
    migrated_services = [
        APP_ROOT / "modules" / "auth" / "service.py",
        APP_ROOT / "modules" / "users" / "service.py",
    ]
    offenders = {
        str(path.relative_to(APP_ROOT)): sorted(
            module for module in _imports(path) if module.startswith("fastapi")
        )
        for path in migrated_services
        if any(module.startswith("fastapi") for module in _imports(path))
    }
    assert offenders == {}


def test_business_case_repository_module_is_a_port_and_compatibility_facade() -> None:
    path = APP_ROOT / "modules" / "business_cases" / "repository.py"
    classes = [
        node.name
        for node in _tree(path).body
        if isinstance(node, ast.ClassDef)
    ]
    assert classes == ["BusinessCaseRepository"]
    assert not any(module.startswith("sqlalchemy") for module in _imports(path))


def test_pipeline_worker_task_is_only_an_executor_adapter() -> None:
    tree = _tree(APP_ROOT / "worker" / "tasks.py")
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "execute_pipeline_run"
    )
    assert len(function.body) == 1
    assert isinstance(function.body[0], ast.Return)


def test_pipeline_step_handler_facade_only_composes_focused_handlers() -> None:
    facade = APP_ROOT / "modules" / "pipelines" / "step_handlers.py"
    classes = [
        node.name
        for node in _tree(facade).body
        if isinstance(node, ast.ClassDef)
    ]
    assert classes == ["PipelineStepHandlerRegistry"]

    focused_modules = [
        "step_contracts.py",
        "data_step_handlers.py",
        "training_step_handler.py",
        "automl_step_handler.py",
        "scoring_step_handler.py",
        "monitoring_step_handler.py",
    ]
    pipeline_root = facade.parent
    assert all((pipeline_root / name).is_file() for name in focused_modules)
    assert all(
        "app.modules.pipelines.step_handlers" not in _imports(pipeline_root / name)
        for name in focused_modules
    )
