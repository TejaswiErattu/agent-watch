import ast
import tomllib
from pathlib import Path

SDK_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = SDK_ROOT / "agentwatch"
FORBIDDEN = {"boto3", "botocore", "numpy", "pandas", "torch"}


def test_import_exposes_version():
    import agentwatch

    assert isinstance(agentwatch.__version__, str)
    assert agentwatch.__version__


def test_single_runtime_dependency_is_requests_with_range():
    with open(SDK_ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    deps = data["project"]["dependencies"]
    assert len(deps) == 1
    dep = deps[0].replace(" ", "")
    assert dep.startswith("requests")
    assert ">=" in dep and "<" in dep


def test_no_heavy_imports_in_package():
    files = list(PACKAGE_DIR.rglob("*.py"))
    assert files, "expected python files under sdk/agentwatch/"
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            assert not FORBIDDEN & set(names), f"{path.name} imports {names}"
