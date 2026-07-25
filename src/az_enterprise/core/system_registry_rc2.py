from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

REGISTRY_VERSION = "0.3.0"

DEFAULT_EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".tox", ".venv", "venv", "env",
    "__pycache__", "node_modules", "dist", "build",
}

ARTIFACT_SUFFIXES = {
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".csv", ".tsv", ".txt", ".md", ".html", ".xml", ".srt", ".vtt",
    ".wav", ".mp3", ".m4a", ".flac", ".aac", ".mp4", ".mov", ".mkv",
    ".avi", ".webm", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".npy",
    ".npz", ".pt", ".pth", ".onnx", ".log",
}

ROLE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("director", re.compile(r"(?:^|[_\-.])director(?:[_\-.]|$)", re.I)),
    ("runtime", re.compile(r"(?:^|[_\-.])runtime(?:[_\-.]|$)", re.I)),
    ("engine", re.compile(r"(?:^|[_\-.])engine(?:[_\-.]|$)", re.I)),
    ("manager", re.compile(r"(?:^|[_\-.])manager(?:[_\-.]|$)", re.I)),
    ("orchestrator", re.compile(r"(?:^|[_\-.])orchestrator(?:[_\-.]|$)", re.I)),
    ("pipeline", re.compile(r"(?:^|[_\-.])pipeline(?:[_\-.]|$)", re.I)),
    ("supervisor", re.compile(r"(?:^|[_\-.])supervisor(?:[_\-.]|$)", re.I)),
    ("policy", re.compile(r"(?:^|[_\-.])policy(?:[_\-.]|$)", re.I)),
    ("registry", re.compile(r"(?:^|[_\-.])registry(?:[_\-.]|$)", re.I)),
    ("monitor", re.compile(r"(?:^|[_\-.])monitor(?:[_\-.]|$)", re.I)),
    ("analyzer", re.compile(r"(?:^|[_\-.])analy[sz]er(?:[_\-.]|$)", re.I)),
    ("renderer", re.compile(r"(?:^|[_\-.])render(?:er)?(?:[_\-.]|$)", re.I)),
    ("composer", re.compile(r"(?:^|[_\-.])composer(?:[_\-.]|$)", re.I)),
    ("resolver", re.compile(r"(?:^|[_\-.])resolver(?:[_\-.]|$)", re.I)),
    ("gateway", re.compile(r"(?:^|[_\-.])gateway(?:[_\-.]|$)", re.I)),
    ("agent", re.compile(r"(?:^|[_\-.])agent(?:[_\-.]|$)", re.I)),
)


@dataclass(slots=True)
class ImportRecord:
    source_module: str
    imported_module: str
    imported_names: list[str] = field(default_factory=list)
    level: int = 0
    lineno: int = 0
    is_internal: bool = False


@dataclass(slots=True)
class FunctionRecord:
    name: str
    lineno: int
    end_lineno: int
    is_async: bool
    decorators: list[str]
    arguments: list[str]
    returns: Optional[str]
    docstring: Optional[str]


@dataclass(slots=True)
class ClassRecord:
    name: str
    qualified_name: str
    module: str
    lineno: int
    end_lineno: int
    bases: list[str]
    decorators: list[str]
    methods: list[FunctionRecord]
    properties: list[str]
    docstring: Optional[str]
    roles: list[str]


@dataclass(slots=True)
class ArtifactReference:
    module: str
    file: str
    value: str
    suffix: str
    operation: str
    lineno: int
    context: str


@dataclass(slots=True)
class ModuleRecord:
    path: str
    module: str
    size_bytes: int
    modified_utc: str
    sha256: str
    line_count: int
    syntax_ok: bool
    syntax_error: Optional[str]
    classes: list[ClassRecord]
    functions: list[FunctionRecord]
    imports: list[ImportRecord]
    roles: list[str]
    artifact_references: list[ArtifactReference]


@dataclass(slots=True)
class ScanProblem:
    path: str
    kind: str
    message: str


def detect_roles(text: str) -> list[str]:
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    normalized = normalized.replace("\\", "_").replace("/", "_")
    return sorted({role for role, pattern in ROLE_RULES if pattern.search(normalized)})


def utc_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def path_to_module(relative_path: Path) -> str:
    parts = list(relative_path.with_suffix("").parts)
    if "src" in parts:
        parts = parts[parts.index("src") + 1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


class PythonAstCollector(ast.NodeVisitor):
    def __init__(self, module_name: str, relative_path: str, internal_prefixes: set[str]) -> None:
        self.module_name = module_name
        self.relative_path = relative_path
        self.internal_prefixes = internal_prefixes
        self.classes: list[ClassRecord] = []
        self.functions: list[FunctionRecord] = []
        self.imports: list[ImportRecord] = []
        self.artifacts: list[ArtifactReference] = []
        self._class_stack: list[str] = []

    @staticmethod
    def expr_text(node: Optional[ast.AST]) -> Optional[str]:
        if node is None:
            return None
        try:
            return ast.unparse(node)
        except Exception:
            return node.__class__.__name__

    @staticmethod
    def decorator_names(node: ast.AST) -> list[str]:
        result: list[str] = []
        for decorator in getattr(node, "decorator_list", []):
            try:
                result.append(ast.unparse(decorator))
            except Exception:
                result.append(decorator.__class__.__name__)
        return result

    @staticmethod
    def argument_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        args = node.args
        result = [arg.arg for arg in args.posonlyargs]
        result.extend(arg.arg for arg in args.args)
        if args.vararg:
            result.append(f"*{args.vararg.arg}")
        result.extend(arg.arg for arg in args.kwonlyargs)
        if args.kwarg:
            result.append(f"**{args.kwarg.arg}")
        return result

    def function_record(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionRecord:
        return FunctionRecord(
            name=node.name,
            lineno=getattr(node, "lineno", 0),
            end_lineno=getattr(node, "end_lineno", getattr(node, "lineno", 0)),
            is_async=isinstance(node, ast.AsyncFunctionDef),
            decorators=self.decorator_names(node),
            arguments=self.argument_names(node),
            returns=self.expr_text(node.returns),
            docstring=ast.get_docstring(node, clean=True),
        )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            imported = alias.name
            self.imports.append(ImportRecord(
                source_module=self.module_name,
                imported_module=imported,
                imported_names=[alias.asname or alias.name],
                lineno=getattr(node, "lineno", 0),
                is_internal=imported.split(".", 1)[0] in self.internal_prefixes,
            ))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        imported = self.resolve_relative_import(node.module or "", node.level)
        self.imports.append(ImportRecord(
            source_module=self.module_name,
            imported_module=imported,
            imported_names=[alias.name for alias in node.names],
            level=node.level,
            lineno=getattr(node, "lineno", 0),
            is_internal=(not imported) or imported.split(".", 1)[0] in self.internal_prefixes,
        ))

    def resolve_relative_import(self, imported: str, level: int) -> str:
        if level <= 0:
            return imported
        package = self.module_name.split(".")[:-1]
        keep = max(0, len(package) - level + 1)
        base = package[:keep]
        if imported:
            base.extend(imported.split("."))
        return ".".join(base)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified = ".".join([*self._class_stack, node.name])
        self._class_stack.append(node.name)
        methods: list[FunctionRecord] = []
        properties: list[str] = []
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method = self.function_record(child)
                methods.append(method)
                if any(d.split("(", 1)[0] == "property" for d in method.decorators):
                    properties.append(method.name)
        bases = [self.expr_text(base) or "" for base in node.bases]
        role_text = " ".join([node.name, qualified, self.module_name, *bases])
        self.classes.append(ClassRecord(
            name=node.name,
            qualified_name=qualified,
            module=self.module_name,
            lineno=getattr(node, "lineno", 0),
            end_lineno=getattr(node, "end_lineno", getattr(node, "lineno", 0)),
            bases=bases,
            decorators=self.decorator_names(node),
            methods=methods,
            properties=properties,
            docstring=ast.get_docstring(node, clean=True),
            roles=detect_roles(role_text),
        ))
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not self._class_stack:
            self.functions.append(self.function_record(node))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if not self._class_stack:
            self.functions.append(self.function_record(node))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        operation = self.call_operation(node)
        values = [*node.args, *[kw.value for kw in node.keywords]]
        for arg in values:
            for value, lineno in self.extract_strings(arg):
                suffix = Path(value).suffix.lower()
                if suffix in ARTIFACT_SUFFIXES:
                    self.artifacts.append(ArtifactReference(
                        module=self.module_name,
                        file=self.relative_path,
                        value=value,
                        suffix=suffix,
                        operation=operation,
                        lineno=lineno or getattr(node, "lineno", 0),
                        context=self.expr_text(node) or "",
                    ))
        self.generic_visit(node)

    def call_operation(self, node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        else:
            name = ""
        if name == "open":
            mode = ""
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = str(kw.value.value)
            return "write" if any(flag in mode for flag in "wax+") else "read"
        if name in {"write_text", "write_bytes", "dump", "save", "savefig", "imwrite", "to_csv", "to_excel", "to_json", "to_parquet"}:
            return "write"
        if name in {"read_text", "read_bytes", "load", "loads", "read_csv", "read_excel", "read_json", "imread"}:
            return "read"
        return "reference"

    def extract_strings(self, node: ast.AST) -> Iterable[tuple[str, int]]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value, getattr(node, "lineno", 0)
        elif isinstance(node, ast.JoinedStr):
            chunks = [v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{...}" for v in node.values]
            yield "".join(chunks), getattr(node, "lineno", 0)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Div)):
            left, right = list(self.extract_strings(node.left)), list(self.extract_strings(node.right))
            for lv, ll in left:
                for rv, rl in right:
                    yield f"{lv}{'/' if isinstance(node.op, ast.Div) else ''}{rv}", ll or rl
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            for item in node.elts:
                yield from self.extract_strings(item)
        elif isinstance(node, ast.Dict):
            for item in [*[k for k in node.keys if k is not None], *node.values]:
                yield from self.extract_strings(item)


def git_tracked_python_files(root: Path) -> list[Path]:
    if not (root / ".git").exists():
        return []
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--", "*.py"],
            check=True, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30,
        )
    except Exception:
        return []
    return sorted(
        [root / line.strip() for line in result.stdout.splitlines() if (root / line.strip()).is_file()],
        key=lambda p: p.as_posix().lower(),
    )


def discover_python_files(root: Path, excluded_dirs: set[str], include_untracked: bool) -> list[Path]:
    tracked = git_tracked_python_files(root)
    if tracked and not include_untracked:
        return tracked
    found: list[Path] = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in excluded_dirs and not name.startswith(".venv")]
        current = Path(current_root)
        for filename in filenames:
            path = current / filename
            if path.suffix.lower() == ".py":
                found.append(path)
    if tracked:
        merged = {p.resolve(): p for p in [*tracked, *found]}
        found = list(merged.values())
    return sorted(found, key=lambda p: p.as_posix().lower())


def infer_internal_prefixes(files: list[Path], root: Path) -> set[str]:
    prefixes = {"az_enterprise"}
    for path in files:
        module = path_to_module(path.relative_to(root))
        if module:
            prefixes.add(module.split(".", 1)[0])
    return prefixes


def deduplicate_artifacts(items: list[ArtifactReference]) -> list[ArtifactReference]:
    seen: set[tuple[str, str, str, int]] = set()
    result: list[ArtifactReference] = []
    for item in items:
        key = (item.value, item.operation, item.file, item.lineno)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def scan_python_module(path: Path, root: Path, internal_prefixes: set[str]) -> tuple[ModuleRecord, list[ScanProblem]]:
    relative = path.relative_to(root)
    module_name = path_to_module(relative)
    stat = path.stat()
    text = safe_read_text(path)
    problems: list[ScanProblem] = []
    classes: list[ClassRecord] = []
    functions: list[FunctionRecord] = []
    imports: list[ImportRecord] = []
    artifacts: list[ArtifactReference] = []
    syntax_ok = True
    syntax_error: Optional[str] = None
    try:
        tree = ast.parse(text, filename=str(relative))
        collector = PythonAstCollector(module_name, relative.as_posix(), internal_prefixes)
        collector.visit(tree)
        classes, functions, imports = collector.classes, collector.functions, collector.imports
        artifacts = deduplicate_artifacts(collector.artifacts)
    except SyntaxError as exc:
        syntax_ok = False
        syntax_error = f"{exc.msg} at line {exc.lineno}, column {exc.offset}"
        problems.append(ScanProblem(relative.as_posix(), "syntax_error", syntax_error))
    except Exception as exc:
        syntax_ok = False
        syntax_error = f"{type(exc).__name__}: {exc}"
        problems.append(ScanProblem(relative.as_posix(), "parse_error", syntax_error))
    role_text = " ".join([relative.as_posix(), module_name, *[c.name for c in classes]])
    return ModuleRecord(
        path=relative.as_posix(), module=module_name, size_bytes=stat.st_size,
        modified_utc=utc_iso(stat.st_mtime), sha256=sha256_file(path),
        line_count=len(text.splitlines()), syntax_ok=syntax_ok,
        syntax_error=syntax_error, classes=classes, functions=functions,
        imports=imports, roles=detect_roles(role_text), artifact_references=artifacts,
    ), problems


def resolve_known_module(imported: str, known: set[str]) -> Optional[str]:
    if imported in known:
        return imported
    candidates = [m for m in known if m.startswith(imported + ".") or imported.startswith(m + ".")]
    return min(candidates, key=len) if candidates else None


def find_dependency_cycles(adjacency: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = lowlink[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in adjacency.get(node, set()):
            if target not in indices:
                visit(target)
                lowlink[node] = min(lowlink[node], lowlink[target])
            elif target in on_stack:
                lowlink[node] = min(lowlink[node], indices[target])
        if lowlink[node] == indices[node]:
            component: list[str] = []
            while stack:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            if len(component) > 1 or (component and component[0] in adjacency.get(component[0], set())):
                components.append(sorted(component))

    for node in adjacency:
        if node not in indices:
            visit(node)
    return sorted(components, key=lambda item: (-len(item), item))


def build_dependency_registry(modules: list[ModuleRecord]) -> dict[str, Any]:
    names = {m.module for m in modules if m.module}
    adjacency = {name: set() for name in names}
    edges: list[dict[str, Any]] = []
    for module in modules:
        for record in module.imports:
            target = resolve_known_module(record.imported_module, names)
            edges.append({
                "source": module.module,
                "target": target or record.imported_module,
                "raw_target": record.imported_module,
                "names": record.imported_names,
                "lineno": record.lineno,
                "internal": bool(target),
            })
            if target and target != module.module:
                adjacency[module.module].add(target)
    incoming = {name: 0 for name in names}
    for targets in adjacency.values():
        for target in targets:
            incoming[target] = incoming.get(target, 0) + 1
    ranked = sorted([
        {"module": name, "incoming_internal": incoming.get(name, 0),
         "outgoing_internal": len(adjacency.get(name, set())),
         "centrality_score": incoming.get(name, 0) + len(adjacency.get(name, set()))}
        for name in names
    ], key=lambda x: (-x["centrality_score"], x["module"]))
    return {
        "edges": edges,
        "internal_edge_count": sum(1 for e in edges if e["internal"]),
        "external_edge_count": sum(1 for e in edges if not e["internal"]),
        "cycles": find_dependency_cycles(adjacency),
        "ranked_modules": ranked,
    }


def build_runtime_registry(modules: list[ModuleRecord]) -> dict[str, Any]:
    by_role: dict[str, list[dict[str, Any]]] = {}
    for module in modules:
        roles = sorted(set(module.roles) | {r for c in module.classes for r in c.roles})
        if not roles:
            continue
        item = {
            "module": module.module,
            "path": module.path,
            "roles": roles,
            "classes": [{
                "name": c.name, "qualified_name": c.qualified_name, "roles": c.roles,
                "bases": c.bases, "methods": [m.name for m in c.methods],
            } for c in module.classes],
        }
        for role in roles:
            by_role.setdefault(role, []).append(item)
    for items in by_role.values():
        items.sort(key=lambda x: x["module"])
    return {"roles": by_role, "role_counts": {k: len(v) for k, v in sorted(by_role.items())}}


def normalize_artifact_key(value: str) -> str:
    return re.sub(r"/+", "/", value.replace("\\", "/")).strip()


def build_artifact_registry(modules: list[ModuleRecord]) -> dict[str, Any]:
    references: list[dict[str, Any]] = []
    grouped: dict[str, dict[str, Any]] = {}
    for module in modules:
        for artifact in module.artifact_references:
            references.append(asdict(artifact))
            key = normalize_artifact_key(artifact.value)
            group = grouped.setdefault(key, {"artifact": key, "suffix": artifact.suffix, "writers": [], "readers": [], "references": []})
            record = {"module": artifact.module, "file": artifact.file, "lineno": artifact.lineno, "value": artifact.value}
            if artifact.operation == "write":
                group["writers"].append(record)
            elif artifact.operation == "read":
                group["readers"].append(record)
            else:
                group["references"].append(record)
    values = sorted(grouped.values(), key=lambda x: x["artifact"])
    return {
        "references": references,
        "artifacts": values,
        "summary": {
            "unique_artifacts": len(values), "references": len(references),
            "with_writers": sum(bool(x["writers"]) for x in values),
            "with_readers": sum(bool(x["readers"]) for x in values),
            "with_both": sum(bool(x["writers"] and x["readers"]) for x in values),
        },
    }


def build_class_registry(modules: list[ModuleRecord]) -> dict[str, Any]:
    classes = [asdict(c) for m in modules for c in m.classes]
    inheritance = [{"class": c["qualified_name"], "base": base} for c in classes for base in c["bases"]]
    by_name: dict[str, list[str]] = {}
    for c in classes:
        by_name.setdefault(c["name"], []).append(c["module"])
    duplicates = {name: sorted(locations) for name, locations in by_name.items() if len(locations) > 1}
    return {
        "classes": classes,
        "inheritance_edges": inheritance,
        "duplicate_class_names": duplicates,
        "summary": {"class_count": len(classes), "inheritance_edge_count": len(inheritance), "duplicate_class_name_count": len(duplicates)},
    }


def build_module_registry(modules: list[ModuleRecord]) -> dict[str, Any]:
    records = []
    for module in modules:
        item = asdict(module)
        item["classes"] = [c.name for c in module.classes]
        item["functions"] = [f.name for f in module.functions]
        item["imports"] = [i.imported_module for i in module.imports]
        item["artifact_references"] = [{"value": a.value, "operation": a.operation, "lineno": a.lineno} for a in module.artifact_references]
        records.append(item)
    return {
        "modules": records,
        "summary": {
            "module_count": len(modules),
            "syntax_ok": sum(m.syntax_ok for m in modules),
            "syntax_errors": sum(not m.syntax_ok for m in modules),
            "total_lines": sum(m.line_count for m in modules),
            "total_size_bytes": sum(m.size_bytes for m in modules),
            "class_count": sum(len(m.classes) for m in modules),
            "function_count": sum(len(m.functions) for m in modules),
            "import_count": sum(len(m.imports) for m in modules),
        },
    }


def json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def markdown_report(root: Path, generated_at: str, module_registry: dict[str, Any], class_registry: dict[str, Any], runtime_registry: dict[str, Any], artifact_registry: dict[str, Any], dependency_registry: dict[str, Any], problems: list[ScanProblem]) -> str:
    summary = module_registry["summary"]
    lines = [
        "# ATLAS ZERO RC2 — System Registry", "",
        f"- Registry version: `{REGISTRY_VERSION}`",
        f"- Generated at: `{generated_at}`",
        f"- Project root: `{root}`", "", "## Summary", "",
        f"- Python modules: **{summary['module_count']}**",
        f"- Total Python lines: **{summary['total_lines']}**",
        f"- Classes: **{summary['class_count']}**",
        f"- Module-level functions: **{summary['function_count']}**",
        f"- Import statements: **{summary['import_count']}**",
        f"- Syntax errors: **{summary['syntax_errors']}**",
        f"- Unique artifact references: **{artifact_registry['summary']['unique_artifacts']}**",
        f"- Internal dependency edges: **{dependency_registry['internal_edge_count']}**",
        f"- Dependency cycles: **{len(dependency_registry['cycles'])}**", "",
        "## Runtime roles", "",
    ]
    if runtime_registry["role_counts"]:
        lines.extend(f"- `{role}`: **{count}**" for role, count in runtime_registry["role_counts"].items())
    else:
        lines.append("- No role-bearing modules detected.")
    lines += ["", "## Most connected modules", ""]
    for item in dependency_registry["ranked_modules"][:25]:
        lines.append(f"- `{item['module']}` — incoming {item['incoming_internal']}, outgoing {item['outgoing_internal']}, score {item['centrality_score']}")
    lines += ["", "## Duplicate class names", ""]
    duplicates = class_registry["duplicate_class_names"]
    if duplicates:
        for name, locations in sorted(duplicates.items())[:50]:
            lines.append(f"- `{name}`: " + ", ".join(f"`{location}`" for location in locations))
    else:
        lines.append("- None detected.")
    lines += ["", "## Dependency cycles", ""]
    if dependency_registry["cycles"]:
        lines.extend("- " + " → ".join(f"`{m}`" for m in cycle) for cycle in dependency_registry["cycles"][:50])
    else:
        lines.append("- None detected.")
    lines += ["", "## Syntax and scan problems", ""]
    if problems:
        lines.extend(f"- `{p.path}` — **{p.kind}**: {p.message}" for p in problems[:100])
    else:
        lines.append("- None detected.")
    lines += ["", "## Generated files", "", "- `system_registry.json`", "- `module_registry.json`", "- `class_registry.json`", "- `runtime_registry.json`", "- `artifact_registry.json`", "- `dependency_registry.json`", "- `architecture_report.md`", ""]
    return "\n".join(lines)


class SystemRegistryRC2:
    """Build a deterministic architecture registry for an ATLAS ZERO repository."""

    def __init__(self, project_root: Path | str, output_dir: Path | str | None = None, *, include_untracked: bool = True, excluded_dirs: Optional[set[str]] = None) -> None:
        self.project_root = Path(project_root).resolve()
        if not self.project_root.exists():
            raise FileNotFoundError(f"Project root does not exist: {self.project_root}")
        if not self.project_root.is_dir():
            raise NotADirectoryError(f"Project root is not a directory: {self.project_root}")
        self.output_dir = Path(output_dir).resolve() if output_dir is not None else self.project_root / "workspace" / "system"
        self.include_untracked = include_untracked
        self.excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)
        if excluded_dirs:
            self.excluded_dirs.update(excluded_dirs)
        try:
            relative_output = self.output_dir.relative_to(self.project_root)
            if relative_output.parts:
                self.excluded_dirs.add(relative_output.parts[0])
        except ValueError:
            pass

    def build(self) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc).isoformat()
        files = discover_python_files(self.project_root, self.excluded_dirs, self.include_untracked)
        internal_prefixes = infer_internal_prefixes(files, self.project_root)
        modules: list[ModuleRecord] = []
        problems: list[ScanProblem] = []
        for index, path in enumerate(files, 1):
            try:
                module, module_problems = scan_python_module(path, self.project_root, internal_prefixes)
                modules.append(module)
                problems.extend(module_problems)
            except Exception as exc:
                relative = path.relative_to(self.project_root).as_posix() if path.is_relative_to(self.project_root) else str(path)
                problems.append(ScanProblem(relative, "scan_error", f"{type(exc).__name__}: {exc}"))
            if index % 50 == 0:
                print(f"[SystemRegistryRC2] scanned {index}/{len(files)} Python files")
        modules.sort(key=lambda x: x.path.lower())
        module_registry = build_module_registry(modules)
        class_registry = build_class_registry(modules)
        runtime_registry = build_runtime_registry(modules)
        artifact_registry = build_artifact_registry(modules)
        dependency_registry = build_dependency_registry(modules)
        system_registry = {
            "schema": "atlas_zero.system_registry.rc2",
            "registry_version": REGISTRY_VERSION,
            "generated_at": generated_at,
            "project_root": str(self.project_root),
            "output_dir": str(self.output_dir),
            "python_version": sys.version,
            "platform": sys.platform,
            "configuration": {"include_untracked": self.include_untracked, "excluded_dirs": sorted(self.excluded_dirs)},
            "summary": {
                **module_registry["summary"],
                "runtime_role_counts": runtime_registry["role_counts"],
                "unique_artifacts": artifact_registry["summary"]["unique_artifacts"],
                "dependency_cycles": len(dependency_registry["cycles"]),
                "scan_problems": len(problems),
            },
            "files": {
                "module_registry": "module_registry.json",
                "class_registry": "class_registry.json",
                "runtime_registry": "runtime_registry.json",
                "artifact_registry": "artifact_registry.json",
                "dependency_registry": "dependency_registry.json",
                "architecture_report": "architecture_report.md",
            },
            "problems": [asdict(p) for p in problems],
        }
        self.output_dir.mkdir(parents=True, exist_ok=True)
        json_dump(self.output_dir / "system_registry.json", system_registry)
        json_dump(self.output_dir / "module_registry.json", module_registry)
        json_dump(self.output_dir / "class_registry.json", class_registry)
        json_dump(self.output_dir / "runtime_registry.json", runtime_registry)
        json_dump(self.output_dir / "artifact_registry.json", artifact_registry)
        json_dump(self.output_dir / "dependency_registry.json", dependency_registry)
        (self.output_dir / "architecture_report.md").write_text(
            markdown_report(self.project_root, generated_at, module_registry, class_registry, runtime_registry, artifact_registry, dependency_registry, problems),
            encoding="utf-8",
        )
        return system_registry



LAYER_ORDER = {
    "registry": 0,
    "policy": 1,
    "resolver": 2,
    "engine": 3,
    "runtime": 4,
    "orchestrator": 5,
    "pipeline": 6,
    "director": 7,
    "composer": 8,
    "renderer": 9,
    "gateway": 10,
}

FORBIDDEN_LAYER_IMPORTS = {
    "registry": {"renderer", "composer", "director", "pipeline", "orchestrator", "runtime"},
    "policy": {"renderer", "composer"},
    "resolver": {"renderer", "composer"},
    "engine": {"gateway"},
    "renderer": {"director"},
}


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required registry file is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * max(0.0, min(1.0, ratio))
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def risk_band(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def module_layer(roles: list[str]) -> str:
    if not roles:
        return "unclassified"
    ranked = sorted(
        roles,
        key=lambda role: LAYER_ORDER.get(role, -1),
        reverse=True,
    )
    return ranked[0]


def module_is_entrypoint(module: dict[str, Any]) -> bool:
    path = str(module.get("path", "")).replace("\\", "/").lower()
    name = str(module.get("module", "")).lower()
    functions = {str(item) for item in module.get("functions", [])}
    roles = set(module.get("roles", []))
    return (
        path.startswith("tests/")
        or path.startswith("tools/")
        or path.startswith("scripts/")
        or path.endswith("/__main__.py")
        or name.endswith(".__main__")
        or "main" in functions
        or bool(roles & {"director", "orchestrator", "pipeline", "gateway"})
    )


class DependencyIntelligenceRC2:
    """Analyze the registries generated by SystemRegistryRC2."""

    def __init__(
        self,
        project_root: Path | str,
        output_dir: Path | str | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.output_dir = (
            Path(output_dir).resolve()
            if output_dir is not None
            else self.project_root / "workspace" / "system"
        )

    def build(self) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc).isoformat()
        module_registry = load_json_object(self.output_dir / "module_registry.json")
        dependency_registry = load_json_object(self.output_dir / "dependency_registry.json")
        runtime_registry = load_json_object(self.output_dir / "runtime_registry.json")

        modules = module_registry.get("modules", [])
        if not isinstance(modules, list):
            raise ValueError("module_registry.json has an invalid modules field")

        module_by_name = {
            str(module.get("module", "")): module
            for module in modules
            if module.get("module")
        }
        names = set(module_by_name)

        outgoing: dict[str, set[str]] = {name: set() for name in names}
        incoming: dict[str, set[str]] = {name: set() for name in names}

        for edge in dependency_registry.get("edges", []):
            if not edge.get("internal"):
                continue
            source = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            if source in names and target in names and source != target:
                outgoing[source].add(target)
                incoming[target].add(source)

        rankings = self._build_rankings(module_by_name, incoming, outgoing)
        critical_nodes = [
            item
            for item in rankings
            if item["risk"] in {"critical", "high"}
        ]
        dead_modules = self._find_dead_modules(module_by_name, incoming, outgoing)
        isolated_modules = [
            item
            for item in dead_modules
            if item["outgoing_internal"] == 0
        ]
        layer_validation = self._validate_layers(
            module_by_name,
            dependency_registry.get("edges", []),
        )
        director_chains = self._build_director_chains(
            module_by_name,
            outgoing,
        )
        duplicate_candidates = self._find_duplicate_candidates(module_by_name)
        architecture_score = self._architecture_score(
            module_count=len(module_by_name),
            rankings=rankings,
            dead_modules=dead_modules,
            isolated_modules=isolated_modules,
            cycles=dependency_registry.get("cycles", []),
            violations=layer_validation["violations"],
        )

        heatmap = {
            "schema": "atlas_zero.dependency_heatmap.rc2",
            "generated_at": generated_at,
            "modules": rankings,
        }
        critical_payload = {
            "schema": "atlas_zero.critical_nodes.rc2",
            "generated_at": generated_at,
            "count": len(critical_nodes),
            "nodes": critical_nodes,
        }
        dead_payload = {
            "schema": "atlas_zero.dead_modules.rc2",
            "generated_at": generated_at,
            "count": len(dead_modules),
            "isolated_count": len(isolated_modules),
            "modules": dead_modules,
        }
        duplicate_payload = {
            "schema": "atlas_zero.duplicate_candidates.rc2",
            "generated_at": generated_at,
            "count": len(duplicate_candidates),
            "candidates": duplicate_candidates,
        }
        chains_payload = {
            "schema": "atlas_zero.director_chains.rc2",
            "generated_at": generated_at,
            "count": len(director_chains),
            "chains": director_chains,
        }
        score_payload = {
            "schema": "atlas_zero.architecture_score.rc2",
            "generated_at": generated_at,
            **architecture_score,
        }

        result = {
            "schema": "atlas_zero.dependency_intelligence.rc2",
            "registry_version": REGISTRY_VERSION,
            "generated_at": generated_at,
            "project_root": str(self.project_root),
            "output_dir": str(self.output_dir),
            "summary": {
                "module_count": len(module_by_name),
                "internal_edges": sum(len(value) for value in outgoing.values()),
                "critical_nodes": len(critical_nodes),
                "dead_modules": len(dead_modules),
                "isolated_modules": len(isolated_modules),
                "layer_violations": len(layer_validation["violations"]),
                "director_chains": len(director_chains),
                "duplicate_candidates": len(duplicate_candidates),
                "architecture_score": architecture_score["score"],
                "architecture_grade": architecture_score["grade"],
            },
            "files": {
                "dependency_heatmap": "dependency_heatmap.json",
                "critical_nodes": "critical_nodes.json",
                "dead_modules": "dead_modules.json",
                "layer_validation": "layer_validation.json",
                "director_chains": "director_chains.json",
                "duplicate_candidates": "duplicate_candidates.json",
                "architecture_score": "architecture_score.json",
                "dependency_intelligence_report": "dependency_intelligence_report.md",
            },
        }

        self.output_dir.mkdir(parents=True, exist_ok=True)
        json_dump(self.output_dir / "dependency_intelligence.json", result)
        json_dump(self.output_dir / "dependency_heatmap.json", heatmap)
        json_dump(self.output_dir / "critical_nodes.json", critical_payload)
        json_dump(self.output_dir / "dead_modules.json", dead_payload)
        json_dump(self.output_dir / "layer_validation.json", layer_validation)
        json_dump(self.output_dir / "director_chains.json", chains_payload)
        json_dump(self.output_dir / "duplicate_candidates.json", duplicate_payload)
        json_dump(self.output_dir / "architecture_score.json", score_payload)
        (self.output_dir / "dependency_intelligence_report.md").write_text(
            self._markdown_report(
                result=result,
                critical_nodes=critical_nodes,
                dead_modules=dead_modules,
                layer_validation=layer_validation,
                director_chains=director_chains,
                duplicate_candidates=duplicate_candidates,
                architecture_score=architecture_score,
            ),
            encoding="utf-8",
        )
        return result

    def _build_rankings(
        self,
        module_by_name: dict[str, dict[str, Any]],
        incoming: dict[str, set[str]],
        outgoing: dict[str, set[str]],
    ) -> list[dict[str, Any]]:
        incoming_values = [len(value) for value in incoming.values()]
        outgoing_values = [len(value) for value in outgoing.values()]
        incoming_p95 = max(1.0, percentile([float(v) for v in incoming_values], 0.95))
        outgoing_p95 = max(1.0, percentile([float(v) for v in outgoing_values], 0.95))

        rankings: list[dict[str, Any]] = []
        for name, module in module_by_name.items():
            in_count = len(incoming[name])
            out_count = len(outgoing[name])
            line_count = int(module.get("line_count", 0) or 0)
            roles = list(module.get("roles", []))
            syntax_ok = bool(module.get("syntax_ok", True))

            normalized_in = min(1.0, in_count / incoming_p95)
            normalized_out = min(1.0, out_count / outgoing_p95)
            size_factor = min(1.0, line_count / 1500.0)
            role_factor = min(
                1.0,
                len(set(roles) & {
                    "director", "runtime", "engine", "orchestrator",
                    "pipeline", "renderer", "registry", "policy",
                }) / 3.0,
            )
            syntax_penalty = 1.0 if not syntax_ok else 0.0

            score = round(
                100.0 * (
                    0.45 * normalized_in
                    + 0.25 * normalized_out
                    + 0.15 * size_factor
                    + 0.10 * role_factor
                    + 0.05 * syntax_penalty
                ),
                2,
            )
            rankings.append(
                {
                    "module": name,
                    "path": module.get("path"),
                    "roles": roles,
                    "layer": module_layer(roles),
                    "incoming_internal": in_count,
                    "outgoing_internal": out_count,
                    "imported_by": sorted(incoming[name]),
                    "imports": sorted(outgoing[name]),
                    "line_count": line_count,
                    "syntax_ok": syntax_ok,
                    "centrality_score": score,
                    "risk": risk_band(score),
                }
            )

        rankings.sort(
            key=lambda item: (
                -item["centrality_score"],
                -item["incoming_internal"],
                item["module"],
            )
        )
        return rankings

    def _find_dead_modules(
        self,
        module_by_name: dict[str, dict[str, Any]],
        incoming: dict[str, set[str]],
        outgoing: dict[str, set[str]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for name, module in module_by_name.items():
            if incoming[name]:
                continue
            if module_is_entrypoint(module):
                continue
            path = str(module.get("path", "")).replace("\\", "/")
            if path.endswith("/__init__.py") or path == "__init__.py":
                continue
            result.append(
                {
                    "module": name,
                    "path": module.get("path"),
                    "roles": module.get("roles", []),
                    "line_count": int(module.get("line_count", 0) or 0),
                    "outgoing_internal": len(outgoing[name]),
                    "reason": "No internal module imports this module; review before removal.",
                    "confidence": "medium",
                }
            )
        result.sort(key=lambda item: (-item["line_count"], item["module"]))
        return result

    def _validate_layers(
        self,
        module_by_name: dict[str, dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        violations: list[dict[str, Any]] = []
        checked = 0

        for edge in edges:
            if not edge.get("internal"):
                continue
            source = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            source_module = module_by_name.get(source)
            target_module = module_by_name.get(target)
            if not source_module or not target_module:
                continue
            checked += 1

            source_roles = set(source_module.get("roles", []))
            target_roles = set(target_module.get("roles", []))
            matched_rules: list[str] = []
            for source_role, forbidden_targets in FORBIDDEN_LAYER_IMPORTS.items():
                if source_role not in source_roles:
                    continue
                for target_role in forbidden_targets:
                    if target_role in target_roles:
                        matched_rules.append(f"{source_role} -> {target_role}")

            if matched_rules:
                violations.append(
                    {
                        "source": source,
                        "target": target,
                        "source_roles": sorted(source_roles),
                        "target_roles": sorted(target_roles),
                        "rules": sorted(set(matched_rules)),
                        "lineno": edge.get("lineno", 0),
                        "severity": "high" if "renderer -> director" in matched_rules else "medium",
                    }
                )

        violations.sort(
            key=lambda item: (
                0 if item["severity"] == "high" else 1,
                item["source"],
                item["target"],
            )
        )
        return {
            "schema": "atlas_zero.layer_validation.rc2",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "rules": {
                source: sorted(targets)
                for source, targets in sorted(FORBIDDEN_LAYER_IMPORTS.items())
            },
            "checked_internal_edges": checked,
            "violation_count": len(violations),
            "violations": violations,
            "note": (
                "Role-based validation is heuristic. Every violation is a review candidate, "
                "not an automatic proof of an architectural defect."
            ),
        }

    def _build_director_chains(
        self,
        module_by_name: dict[str, dict[str, Any]],
        outgoing: dict[str, set[str]],
    ) -> list[dict[str, Any]]:
        preferred_roles = {
            "director", "orchestrator", "pipeline", "runtime",
            "engine", "composer", "renderer", "gateway",
        }
        starts = [
            name
            for name, module in module_by_name.items()
            if set(module.get("roles", [])) & {"director", "orchestrator", "pipeline"}
        ]
        chains: list[dict[str, Any]] = []

        for start in sorted(starts):
            queue: list[tuple[str, list[str]]] = [(start, [start])]
            found: list[list[str]] = []
            visited_depth: dict[str, int] = {start: 0}

            while queue and len(found) < 25:
                current, path = queue.pop(0)
                if len(path) >= 7:
                    found.append(path)
                    continue

                candidates = [
                    target
                    for target in outgoing.get(current, set())
                    if set(module_by_name[target].get("roles", [])) & preferred_roles
                    and target not in path
                ]
                if not candidates:
                    if len(path) > 1:
                        found.append(path)
                    continue

                candidates.sort(
                    key=lambda target: (
                        -LAYER_ORDER.get(
                            module_layer(module_by_name[target].get("roles", [])),
                            -1,
                        ),
                        target,
                    )
                )
                for target in candidates[:8]:
                    depth = len(path)
                    if visited_depth.get(target, 999) < depth - 1:
                        continue
                    visited_depth[target] = depth
                    queue.append((target, [*path, target]))

            unique_paths: list[list[str]] = []
            seen: set[tuple[str, ...]] = set()
            for path in found:
                key = tuple(path)
                if key not in seen:
                    seen.add(key)
                    unique_paths.append(path)

            chains.append(
                {
                    "start": start,
                    "start_roles": module_by_name[start].get("roles", []),
                    "paths": [
                        {
                            "modules": path,
                            "roles": [
                                module_by_name[module].get("roles", [])
                                for module in path
                            ],
                        }
                        for path in unique_paths[:10]
                    ],
                }
            )
        return chains

    def _find_duplicate_candidates(
        self,
        module_by_name: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        buckets: dict[str, list[dict[str, Any]]] = {}
        stop_tokens = {
            "rc1", "rc2", "alpha", "beta", "final", "new", "old",
            "v1", "v2", "v3", "core", "src", "tools", "test", "tests",
        }

        for name, module in module_by_name.items():
            stem = Path(str(module.get("path", ""))).stem.lower()
            tokens = [
                token
                for token in re.split(r"[^a-z0-9]+", stem)
                if token and token not in stop_tokens and not token.isdigit()
            ]
            signature = "_".join(tokens)
            if len(signature) < 5:
                continue
            buckets.setdefault(signature, []).append(module)

        candidates: list[dict[str, Any]] = []
        for signature, members in buckets.items():
            if len(members) < 2:
                continue
            candidates.append(
                {
                    "signature": signature,
                    "confidence": "medium",
                    "modules": [
                        {
                            "module": member.get("module"),
                            "path": member.get("path"),
                            "line_count": member.get("line_count", 0),
                            "sha256": member.get("sha256"),
                        }
                        for member in sorted(
                            members,
                            key=lambda item: str(item.get("module", "")),
                        )
                    ],
                    "reason": "Normalized module filenames are similar.",
                }
            )

        candidates.sort(
            key=lambda item: (-len(item["modules"]), item["signature"])
        )
        return candidates

    def _architecture_score(
        self,
        *,
        module_count: int,
        rankings: list[dict[str, Any]],
        dead_modules: list[dict[str, Any]],
        isolated_modules: list[dict[str, Any]],
        cycles: list[list[str]],
        violations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        denominator = max(1, module_count)
        critical_count = sum(1 for item in rankings if item["risk"] == "critical")
        high_count = sum(1 for item in rankings if item["risk"] == "high")
        dead_ratio = len(dead_modules) / denominator
        isolated_ratio = len(isolated_modules) / denominator
        critical_ratio = critical_count / denominator
        high_ratio = high_count / denominator
        violation_ratio = len(violations) / denominator

        deductions = {
            "dependency_cycles": min(35.0, len(cycles) * 8.0),
            "critical_nodes": min(15.0, critical_ratio * 100.0),
            "high_risk_nodes": min(10.0, high_ratio * 40.0),
            "dead_modules": min(15.0, dead_ratio * 30.0),
            "isolated_modules": min(10.0, isolated_ratio * 25.0),
            "layer_violations": min(15.0, violation_ratio * 35.0),
        }
        score = round(max(0.0, 100.0 - sum(deductions.values())), 2)
        if score >= 90:
            grade = "A"
        elif score >= 80:
            grade = "B"
        elif score >= 70:
            grade = "C"
        elif score >= 60:
            grade = "D"
        else:
            grade = "E"

        return {
            "score": score,
            "grade": grade,
            "deductions": {key: round(value, 2) for key, value in deductions.items()},
            "metrics": {
                "module_count": module_count,
                "dependency_cycles": len(cycles),
                "critical_nodes": critical_count,
                "high_risk_nodes": high_count,
                "dead_modules": len(dead_modules),
                "isolated_modules": len(isolated_modules),
                "layer_violations": len(violations),
            },
            "interpretation": (
                "Heuristic architecture score for trend tracking. "
                "It must not be used as the sole basis for deleting or rewriting modules."
            ),
        }

    def _markdown_report(
        self,
        *,
        result: dict[str, Any],
        critical_nodes: list[dict[str, Any]],
        dead_modules: list[dict[str, Any]],
        layer_validation: dict[str, Any],
        director_chains: list[dict[str, Any]],
        duplicate_candidates: list[dict[str, Any]],
        architecture_score: dict[str, Any],
    ) -> str:
        summary = result["summary"]
        lines = [
            "# ATLAS ZERO RC2 — Dependency Intelligence",
            "",
            f"- Generated at: `{result['generated_at']}`",
            f"- Architecture score: **{architecture_score['score']} / 100 ({architecture_score['grade']})**",
            "",
            "## Summary",
            "",
            f"- Modules: **{summary['module_count']}**",
            f"- Internal dependency edges: **{summary['internal_edges']}**",
            f"- Critical nodes: **{summary['critical_nodes']}**",
            f"- Dead-module candidates: **{summary['dead_modules']}**",
            f"- Isolated-module candidates: **{summary['isolated_modules']}**",
            f"- Layer violations: **{summary['layer_violations']}**",
            f"- Director chains: **{summary['director_chains']}**",
            f"- Duplicate candidates: **{summary['duplicate_candidates']}**",
            "",
            "## Critical nodes",
            "",
        ]
        if critical_nodes:
            for item in critical_nodes[:40]:
                lines.append(
                    f"- `{item['module']}` — score {item['centrality_score']}, "
                    f"risk `{item['risk']}`, incoming {item['incoming_internal']}, "
                    f"outgoing {item['outgoing_internal']}"
                )
        else:
            lines.append("- None detected.")

        lines += ["", "## Dead-module candidates", ""]
        if dead_modules:
            for item in dead_modules[:60]:
                lines.append(
                    f"- `{item['module']}` — {item['line_count']} lines, "
                    f"outgoing {item['outgoing_internal']}"
                )
        else:
            lines.append("- None detected.")

        lines += ["", "## Layer validation", ""]
        if layer_validation["violations"]:
            for item in layer_validation["violations"][:60]:
                lines.append(
                    f"- `{item['source']}` → `{item['target']}` — "
                    f"{', '.join(item['rules'])} ({item['severity']})"
                )
        else:
            lines.append("- No heuristic violations detected.")

        lines += ["", "## Director chains", ""]
        for chain in director_chains[:30]:
            lines.append(f"### `{chain['start']}`")
            if not chain["paths"]:
                lines.append("- No role-bearing downstream path detected.")
            for path in chain["paths"][:5]:
                lines.append("- " + " → ".join(f"`{item}`" for item in path["modules"]))
            lines.append("")

        lines += ["## Duplicate candidates", ""]
        if duplicate_candidates:
            for item in duplicate_candidates[:40]:
                modules = ", ".join(
                    f"`{member['module']}`" for member in item["modules"]
                )
                lines.append(f"- `{item['signature']}`: {modules}")
        else:
            lines.append("- None detected.")

        lines += [
            "",
            "## Important note",
            "",
            "Dead modules, duplicates, layers and chains are heuristic review candidates. "
            "No file should be deleted or rewritten without a source-level review and tests.",
            "",
        ]
        return "\n".join(lines)



def stable_node_id(node_type: str, value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._:/-]+", "_", value.strip())
    digest = hashlib.sha256(f"{node_type}:{value}".encode("utf-8")).hexdigest()[:12]
    return f"{node_type}:{normalized[:120]}:{digest}"


def classify_module_state(module: dict[str, Any], incoming_count: int) -> list[str]:
    path = str(module.get("path", "")).replace("\\", "/").lower()
    states: list[str] = []
    if not bool(module.get("syntax_ok", True)):
        states.append("syntax_error")
    if any(part in path for part in (
        "archive/", "archived/", "backup/", "backups/", "legacy/",
        "audit_", "/audit/", "target_files/", "finalization/",
    )):
        states.append("archive")
    if any(part in path for part in (
        "generated/", "build/", "dist/", "_generated", "workspace/",
    )):
        states.append("generated")
    if path.startswith("tests/") or "/tests/" in path:
        states.append("test")
    if path.startswith("tools/") or "/tools/" in path:
        states.append("tool")
    if incoming_count == 0 and not module_is_entrypoint(module):
        states.append("orphan")
    if not states:
        states.append("active")
    elif "active" not in states and bool(module.get("syntax_ok", True)):
        states.append("active")
    return sorted(set(states))


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


class ProjectKnowledgeGraphRC2:
    """Build a unified knowledge graph from all Stage 0.1 and 0.2 registries."""

    def __init__(
        self,
        project_root: Path | str,
        output_dir: Path | str | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.output_dir = (
            Path(output_dir).resolve()
            if output_dir is not None
            else self.project_root / "workspace" / "system"
        )

    def build(self) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc).isoformat()

        system_registry = load_json_object(self.output_dir / "system_registry.json")
        module_registry = load_json_object(self.output_dir / "module_registry.json")
        class_registry = load_json_object(self.output_dir / "class_registry.json")
        runtime_registry = load_json_object(self.output_dir / "runtime_registry.json")
        artifact_registry = load_json_object(self.output_dir / "artifact_registry.json")
        dependency_registry = load_json_object(self.output_dir / "dependency_registry.json")
        dependency_intelligence = self._optional_json("dependency_intelligence.json")
        critical_nodes_payload = self._optional_json("critical_nodes.json")

        modules = module_registry.get("modules", [])
        classes = class_registry.get("classes", [])
        artifacts = artifact_registry.get("artifacts", [])
        dependency_edges = dependency_registry.get("edges", [])

        if not isinstance(modules, list):
            raise ValueError("module_registry.json has an invalid modules field")
        if not isinstance(classes, list):
            raise ValueError("class_registry.json has an invalid classes field")
        if not isinstance(artifacts, list):
            raise ValueError("artifact_registry.json has an invalid artifacts field")

        module_nodes, path_to_node, name_to_nodes, exclusions = self._build_module_nodes(
            modules,
            dependency_intelligence,
            critical_nodes_payload,
        )
        class_nodes, class_edges = self._build_class_nodes(classes, name_to_nodes)
        artifact_nodes, artifact_edges = self._build_artifact_nodes(
            artifacts,
            name_to_nodes,
        )
        role_nodes, role_edges = self._build_role_nodes(runtime_registry, name_to_nodes)
        import_edges, unresolved_imports = self._build_import_edges(
            dependency_edges,
            name_to_nodes,
        )
        inheritance_edges = self._build_inheritance_edges(
            class_registry.get("inheritance_edges", []),
            class_nodes,
        )

        nodes = module_nodes + class_nodes + artifact_nodes + role_nodes
        edges = (
            import_edges
            + class_edges
            + artifact_edges
            + role_edges
            + inheritance_edges
        )

        similarity_payload = self._build_similarity_graph(modules, path_to_node)
        edges.extend(similarity_payload["edges"])

        knowledge_paths = self._build_knowledge_paths(nodes, edges)
        node_health = self._build_node_health(nodes, edges)
        topology = self._build_topology(nodes, edges)
        statistics = self._build_statistics(
            nodes=nodes,
            edges=edges,
            modules=modules,
            name_to_nodes=name_to_nodes,
            exclusions=exclusions,
            unresolved_imports=unresolved_imports,
            similarity_count=len(similarity_payload["edges"]),
        )

        graph = {
            "schema": "atlas_zero.project_knowledge_graph.rc2",
            "registry_version": REGISTRY_VERSION,
            "generated_at": generated_at,
            "project_root": str(self.project_root),
            "output_dir": str(self.output_dir),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes,
            "edges": edges,
            "statistics": statistics,
            "source_files": [
                "system_registry.json",
                "module_registry.json",
                "class_registry.json",
                "runtime_registry.json",
                "artifact_registry.json",
                "dependency_registry.json",
                "dependency_intelligence.json",
                "critical_nodes.json",
            ],
        }

        summary = {
            "schema": "atlas_zero.knowledge_graph_summary.rc2",
            "registry_version": REGISTRY_VERSION,
            "generated_at": generated_at,
            "project_root": str(self.project_root),
            "output_dir": str(self.output_dir),
            "summary": statistics,
            "files": {
                "knowledge_graph": "knowledge_graph.json",
                "knowledge_nodes": "knowledge_nodes.json",
                "knowledge_edges": "knowledge_edges.json",
                "knowledge_paths": "knowledge_paths.json",
                "node_health": "node_health.json",
                "similarity_graph": "similarity_graph.json",
                "graph_statistics": "graph_statistics.json",
                "project_topology": "project_topology.json",
                "knowledge_graph_report": "knowledge_graph_report.md",
            },
        }

        self.output_dir.mkdir(parents=True, exist_ok=True)
        json_dump(self.output_dir / "knowledge_graph.json", graph)
        json_dump(
            self.output_dir / "knowledge_nodes.json",
            {
                "schema": "atlas_zero.knowledge_nodes.rc2",
                "generated_at": generated_at,
                "count": len(nodes),
                "nodes": nodes,
            },
        )
        json_dump(
            self.output_dir / "knowledge_edges.json",
            {
                "schema": "atlas_zero.knowledge_edges.rc2",
                "generated_at": generated_at,
                "count": len(edges),
                "edges": edges,
            },
        )
        json_dump(self.output_dir / "knowledge_paths.json", knowledge_paths)
        json_dump(self.output_dir / "node_health.json", node_health)
        json_dump(self.output_dir / "similarity_graph.json", similarity_payload)
        json_dump(self.output_dir / "graph_statistics.json", statistics)
        json_dump(self.output_dir / "project_topology.json", topology)
        json_dump(self.output_dir / "project_knowledge_graph.json", summary)
        (self.output_dir / "knowledge_graph_report.md").write_text(
            self._markdown_report(
                summary=summary,
                statistics=statistics,
                topology=topology,
                knowledge_paths=knowledge_paths,
                similarity_payload=similarity_payload,
                exclusions=exclusions,
                unresolved_imports=unresolved_imports,
                system_registry=system_registry,
            ),
            encoding="utf-8",
        )
        return summary

    def _optional_json(self, filename: str) -> dict[str, Any]:
        path = self.output_dir / filename
        if not path.exists():
            return {}
        try:
            return load_json_object(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _build_module_nodes(
        self,
        modules: list[dict[str, Any]],
        dependency_intelligence: dict[str, Any],
        critical_nodes_payload: dict[str, Any],
    ) -> tuple[
        list[dict[str, Any]],
        dict[str, str],
        dict[str, list[str]],
        list[dict[str, Any]],
    ]:
        rankings = {}
        heatmap_path = self.output_dir / "dependency_heatmap.json"
        if heatmap_path.exists():
            heatmap = self._optional_json("dependency_heatmap.json")
            for item in heatmap.get("modules", []):
                rankings[str(item.get("module", ""))] = item

        critical_names = {
            str(item.get("module", ""))
            for item in critical_nodes_payload.get("nodes", [])
        }

        name_counts: dict[str, int] = {}
        for module in modules:
            name = str(module.get("module", "")).strip()
            if name:
                name_counts[name] = name_counts.get(name, 0) + 1

        incoming_by_name: dict[str, int] = {}
        for item in rankings.values():
            incoming_by_name[str(item.get("module", ""))] = int(
                item.get("incoming_internal", 0) or 0
            )

        nodes: list[dict[str, Any]] = []
        path_to_node: dict[str, str] = {}
        name_to_nodes: dict[str, list[str]] = {}
        exclusions: list[dict[str, Any]] = []

        for index, module in enumerate(modules):
            path = str(module.get("path", "")).replace("\\", "/")
            logical_name = str(module.get("module", "")).strip()
            identity = path or logical_name or f"unknown-module-{index}"
            node_id = stable_node_id("module", identity)
            path_to_node[path] = node_id
            if logical_name:
                name_to_nodes.setdefault(logical_name, []).append(node_id)

            ranking = rankings.get(logical_name, {})
            incoming_count = int(ranking.get("incoming_internal", 0) or 0)
            outgoing_count = int(ranking.get("outgoing_internal", 0) or 0)
            states = classify_module_state(module, incoming_count)

            participation = "full"
            reasons: list[str] = []
            if not logical_name:
                participation = "file_only"
                reasons.append("missing_logical_module_name")
            if logical_name and name_counts.get(logical_name, 0) > 1:
                participation = "ambiguous_name"
                reasons.append("duplicate_logical_module_name")
            if not bool(module.get("syntax_ok", True)):
                reasons.append("syntax_error")
            if reasons:
                exclusions.append(
                    {
                        "path": path,
                        "module": logical_name,
                        "graph_participation": participation,
                        "reasons": reasons,
                    }
                )

            importance = float(ranking.get("centrality_score", 0.0) or 0.0)
            stability = 100.0 if bool(module.get("syntax_ok", True)) else 20.0
            if "archive" in states:
                stability = min(stability, 55.0)
            if "orphan" in states:
                stability = min(stability, 70.0)
            complexity = min(
                100.0,
                round(
                    float(module.get("line_count", 0) or 0) / 15.0
                    + len(module.get("classes", [])) * 4.0
                    + len(module.get("functions", [])) * 2.0,
                    2,
                ),
            )
            connectivity = min(
                100.0,
                round((incoming_count + outgoing_count) * 4.0, 2),
            )
            health = round(
                max(
                    0.0,
                    min(
                        100.0,
                        0.45 * stability
                        + 0.25 * (100.0 - complexity)
                        + 0.20 * min(100.0, connectivity + 25.0)
                        + 0.10 * (100.0 - importance * 0.25),
                    ),
                ),
                2,
            )

            nodes.append(
                {
                    "id": node_id,
                    "type": "module",
                    "label": logical_name or Path(path).stem or identity,
                    "state": states,
                    "properties": {
                        "path": path,
                        "module": logical_name,
                        "logical_name_collision_count": name_counts.get(logical_name, 0),
                        "graph_participation": participation,
                        "syntax_ok": bool(module.get("syntax_ok", True)),
                        "syntax_error": module.get("syntax_error"),
                        "roles": module.get("roles", []),
                        "classes": module.get("classes", []),
                        "functions": module.get("functions", []),
                        "line_count": int(module.get("line_count", 0) or 0),
                        "size_bytes": int(module.get("size_bytes", 0) or 0),
                        "sha256": module.get("sha256"),
                        "critical": logical_name in critical_names,
                    },
                    "metrics": {
                        "importance": round(importance, 2),
                        "connectivity": connectivity,
                        "stability": stability,
                        "complexity": complexity,
                        "health": health,
                        "incoming_internal": incoming_count,
                        "outgoing_internal": outgoing_count,
                    },
                }
            )

        return nodes, path_to_node, name_to_nodes, exclusions

    def _build_class_nodes(
        self,
        classes: list[dict[str, Any]],
        name_to_nodes: dict[str, list[str]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for item in classes:
            qualified = str(item.get("qualified_name", "")).strip()
            if not qualified:
                module_name = str(item.get("module", "")).strip()
                class_name = str(item.get("name", "")).strip()
                qualified = f"{module_name}.{class_name}".strip(".")
            node_id = stable_node_id("class", qualified)
            nodes.append(
                {
                    "id": node_id,
                    "type": "class",
                    "label": item.get("name") or qualified,
                    "state": ["active"],
                    "properties": {
                        "qualified_name": qualified,
                        "module": item.get("module"),
                        "file": item.get("file"),
                        "lineno": item.get("lineno"),
                        "bases": item.get("bases", []),
                        "roles": item.get("roles", []),
                        "methods": [
                            method.get("name") if isinstance(method, dict) else method
                            for method in item.get("methods", [])
                        ],
                    },
                    "metrics": {
                        "importance": 0.0,
                        "connectivity": 0.0,
                        "stability": 100.0,
                        "complexity": min(100.0, len(item.get("methods", [])) * 5.0),
                        "health": 90.0,
                    },
                }
            )
            for module_node in name_to_nodes.get(str(item.get("module", "")), []):
                edges.append(
                    self._edge(
                        source=module_node,
                        target=node_id,
                        relation="contains",
                        evidence="class_registry",
                        confidence=1.0,
                    )
                )
        return nodes, edges

    def _build_artifact_nodes(
        self,
        artifacts: list[dict[str, Any]],
        name_to_nodes: dict[str, list[str]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for artifact in artifacts:
            value = str(artifact.get("artifact", "")).strip()
            if not value:
                continue
            node_id = stable_node_id("artifact", value)
            states = ["referenced"]
            if artifact.get("writers"):
                states.append("generated")
            nodes.append(
                {
                    "id": node_id,
                    "type": "artifact",
                    "label": Path(value).name or value,
                    "state": sorted(set(states)),
                    "properties": {
                        "artifact": value,
                        "suffix": artifact.get("suffix"),
                        "writer_count": len(artifact.get("writers", [])),
                        "reader_count": len(artifact.get("readers", [])),
                        "reference_count": len(artifact.get("references", [])),
                    },
                    "metrics": {
                        "importance": min(
                            100.0,
                            (
                                len(artifact.get("writers", []))
                                + len(artifact.get("readers", []))
                                + len(artifact.get("references", []))
                            ) * 8.0,
                        ),
                        "connectivity": 0.0,
                        "stability": 80.0,
                        "complexity": 0.0,
                        "health": 85.0,
                    },
                }
            )
            for relation_name, key in (
                ("writes", "writers"),
                ("reads", "readers"),
                ("references", "references"),
            ):
                for ref in artifact.get(key, []):
                    module_name = str(ref.get("module", ""))
                    for module_node in name_to_nodes.get(module_name, []):
                        edges.append(
                            self._edge(
                                source=module_node,
                                target=node_id,
                                relation=relation_name,
                                evidence="artifact_registry",
                                confidence=1.0 if len(name_to_nodes.get(module_name, [])) == 1 else 0.65,
                                metadata={"lineno": ref.get("lineno")},
                            )
                        )
        return nodes, edges

    def _build_role_nodes(
        self,
        runtime_registry: dict[str, Any],
        name_to_nodes: dict[str, list[str]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for role, members in sorted(runtime_registry.get("roles", {}).items()):
            role_id = stable_node_id("role", role)
            nodes.append(
                {
                    "id": role_id,
                    "type": "role",
                    "label": role,
                    "state": ["active"],
                    "properties": {"role": role, "member_count": len(members)},
                    "metrics": {
                        "importance": min(100.0, len(members) * 4.0),
                        "connectivity": min(100.0, len(members) * 4.0),
                        "stability": 100.0,
                        "complexity": 0.0,
                        "health": 95.0,
                    },
                }
            )
            for member in members:
                module_name = str(member.get("module", ""))
                for module_node in name_to_nodes.get(module_name, []):
                    edges.append(
                        self._edge(
                            source=module_node,
                            target=role_id,
                            relation="has_role",
                            evidence="runtime_registry",
                            confidence=1.0 if len(name_to_nodes.get(module_name, [])) == 1 else 0.65,
                        )
                    )
        return nodes, edges

    def _build_import_edges(
        self,
        dependency_edges: list[dict[str, Any]],
        name_to_nodes: dict[str, list[str]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        edges: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        for item in dependency_edges:
            if not item.get("internal"):
                continue
            source_name = str(item.get("source", ""))
            target_name = str(item.get("target", ""))
            source_nodes = name_to_nodes.get(source_name, [])
            target_nodes = name_to_nodes.get(target_name, [])
            if not source_nodes or not target_nodes:
                unresolved.append(
                    {
                        "source": source_name,
                        "target": target_name,
                        "lineno": item.get("lineno"),
                        "reason": (
                            "source_not_mapped" if not source_nodes
                            else "target_not_mapped"
                        ),
                    }
                )
                continue
            ambiguity = len(source_nodes) * len(target_nodes)
            confidence = 1.0 if ambiguity == 1 else round(1.0 / ambiguity, 4)
            for source_node in source_nodes:
                for target_node in target_nodes:
                    if source_node == target_node:
                        continue
                    edges.append(
                        self._edge(
                            source=source_node,
                            target=target_node,
                            relation="imports",
                            evidence="dependency_registry",
                            confidence=confidence,
                            metadata={
                                "lineno": item.get("lineno"),
                                "ambiguous_mapping": ambiguity > 1,
                            },
                        )
                    )
        return edges, unresolved

    def _build_inheritance_edges(
        self,
        inheritance: list[dict[str, Any]],
        class_nodes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        by_qualified = {
            str(node.get("properties", {}).get("qualified_name", "")): node["id"]
            for node in class_nodes
        }
        by_short: dict[str, list[str]] = {}
        for node in class_nodes:
            short = str(node.get("label", ""))
            by_short.setdefault(short, []).append(node["id"])

        edges: list[dict[str, Any]] = []
        for item in inheritance:
            child = str(item.get("class", ""))
            base = str(item.get("base", ""))
            child_id = by_qualified.get(child)
            base_candidates = (
                [by_qualified[base]]
                if base in by_qualified
                else by_short.get(base.split(".")[-1], [])
            )
            if not child_id or not base_candidates:
                continue
            confidence = 1.0 if len(base_candidates) == 1 else 0.5
            for base_id in base_candidates:
                edges.append(
                    self._edge(
                        source=child_id,
                        target=base_id,
                        relation="extends",
                        evidence="class_registry",
                        confidence=confidence,
                    )
                )
        return edges

    def _build_similarity_graph(
        self,
        modules: list[dict[str, Any]],
        path_to_node: dict[str, str],
    ) -> dict[str, Any]:
        profiles: list[dict[str, Any]] = []
        for module in modules:
            path = str(module.get("path", "")).replace("\\", "/")
            profiles.append(
                {
                    "node": path_to_node.get(path),
                    "path": path,
                    "module": str(module.get("module", "")),
                    "stem": Path(path).stem.lower(),
                    "imports": set(str(value) for value in module.get("imports", [])),
                    "classes": set(str(value) for value in module.get("classes", [])),
                    "roles": set(str(value) for value in module.get("roles", [])),
                    "artifacts": set(
                        str(item.get("value", ""))
                        for item in module.get("artifact_references", [])
                        if isinstance(item, dict)
                    ),
                }
            )

        candidates: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for left_index, left in enumerate(profiles):
            if not left["node"]:
                continue
            left_tokens = set(re.split(r"[^a-z0-9]+", left["stem"])) - {""}
            for right in profiles[left_index + 1:]:
                if not right["node"]:
                    continue
                right_tokens = set(re.split(r"[^a-z0-9]+", right["stem"])) - {""}
                name_score = jaccard_similarity(left_tokens, right_tokens)
                import_score = jaccard_similarity(left["imports"], right["imports"])
                class_score = jaccard_similarity(left["classes"], right["classes"])
                role_score = jaccard_similarity(left["roles"], right["roles"])
                artifact_score = jaccard_similarity(left["artifacts"], right["artifacts"])

                evidence_present = (
                    bool(left["imports"] or right["imports"])
                    or bool(left["classes"] or right["classes"])
                    or bool(left["roles"] or right["roles"])
                    or bool(left["artifacts"] or right["artifacts"])
                )
                score = (
                    0.30 * name_score
                    + 0.25 * import_score
                    + 0.20 * class_score
                    + 0.15 * role_score
                    + 0.10 * artifact_score
                )
                if not evidence_present:
                    score = 0.30 * name_score
                score = round(score * 100.0, 2)
                if score < 58.0:
                    continue

                confidence = "high" if score >= 82 else "medium"
                candidate = {
                    "left_node": left["node"],
                    "right_node": right["node"],
                    "left_path": left["path"],
                    "right_path": right["path"],
                    "similarity_score": score,
                    "confidence": confidence,
                    "components": {
                        "name": round(name_score * 100.0, 2),
                        "imports": round(import_score * 100.0, 2),
                        "classes": round(class_score * 100.0, 2),
                        "roles": round(role_score * 100.0, 2),
                        "artifacts": round(artifact_score * 100.0, 2),
                    },
                }
                candidates.append(candidate)
                edges.append(
                    self._edge(
                        source=left["node"],
                        target=right["node"],
                        relation="similar_to",
                        evidence="knowledge_graph_similarity",
                        confidence=round(score / 100.0, 4),
                        metadata=candidate["components"],
                    )
                )

        candidates.sort(
            key=lambda item: (-item["similarity_score"], item["left_path"], item["right_path"])
        )
        edges.sort(
            key=lambda item: (-item["confidence"], item["source"], item["target"])
        )
        return {
            "schema": "atlas_zero.similarity_graph.rc2",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "threshold": 58.0,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "edges": edges,
            "note": "Similarity is heuristic and is not proof that modules are duplicates.",
        }

    def _build_knowledge_paths(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        node_by_id = {node["id"]: node for node in nodes}
        adjacency: dict[str, list[dict[str, Any]]] = {}
        allowed = {"imports", "writes", "reads", "references", "contains", "has_role"}
        for edge in edges:
            if edge["relation"] in allowed:
                adjacency.setdefault(edge["source"], []).append(edge)

        starts = [
            node
            for node in nodes
            if node["type"] == "module"
            and set(node.get("properties", {}).get("roles", []))
            & {"director", "orchestrator", "pipeline"}
        ]
        paths: list[dict[str, Any]] = []
        seen_paths: set[tuple[str, ...]] = set()

        for start in starts:
            queue: list[tuple[str, list[str], list[str]]] = [
                (start["id"], [start["id"]], [])
            ]
            while queue and len(paths) < 500:
                current, node_path, relation_path = queue.pop(0)
                if len(node_path) >= 7:
                    key = tuple(node_path)
                    if key not in seen_paths:
                        seen_paths.add(key)
                        paths.append(
                            self._path_record(node_path, relation_path, node_by_id)
                        )
                    continue
                outgoing = adjacency.get(current, [])
                if not outgoing:
                    if len(node_path) >= 3:
                        key = tuple(node_path)
                        if key not in seen_paths:
                            seen_paths.add(key)
                            paths.append(
                                self._path_record(node_path, relation_path, node_by_id)
                            )
                    continue
                for edge in outgoing[:20]:
                    target = edge["target"]
                    if target in node_path:
                        continue
                    queue.append(
                        (
                            target,
                            [*node_path, target],
                            [*relation_path, edge["relation"]],
                        )
                    )

        paths.sort(key=lambda item: (-len(item["nodes"]), item["labels"]))
        return {
            "schema": "atlas_zero.knowledge_paths.rc2",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(paths),
            "paths": paths[:500],
        }

    def _path_record(
        self,
        node_path: list[str],
        relation_path: list[str],
        node_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        labels = [str(node_by_id[node_id].get("label", node_id)) for node_id in node_path]
        return {
            "nodes": node_path,
            "relations": relation_path,
            "labels": labels,
            "display": " -> ".join(labels),
        }

    def _build_node_health(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        incoming: dict[str, int] = {}
        outgoing: dict[str, int] = {}
        for edge in edges:
            outgoing[edge["source"]] = outgoing.get(edge["source"], 0) + 1
            incoming[edge["target"]] = incoming.get(edge["target"], 0) + 1

        records: list[dict[str, Any]] = []
        for node in nodes:
            metrics = dict(node.get("metrics", {}))
            total_connectivity = incoming.get(node["id"], 0) + outgoing.get(node["id"], 0)
            metrics["graph_incoming"] = incoming.get(node["id"], 0)
            metrics["graph_outgoing"] = outgoing.get(node["id"], 0)
            metrics["graph_connectivity"] = total_connectivity
            records.append(
                {
                    "node_id": node["id"],
                    "type": node["type"],
                    "label": node["label"],
                    "state": node.get("state", []),
                    "metrics": metrics,
                }
            )
        records.sort(
            key=lambda item: (
                float(item["metrics"].get("health", 0.0)),
                -int(item["metrics"].get("graph_connectivity", 0)),
                item["label"],
            )
        )
        return {
            "schema": "atlas_zero.node_health.rc2",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(records),
            "nodes": records,
        }

    def _build_topology(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        by_type: dict[str, list[str]] = {}
        for node in nodes:
            by_type.setdefault(node["type"], []).append(node["id"])
        relation_counts: dict[str, int] = {}
        for edge in edges:
            relation_counts[edge["relation"]] = relation_counts.get(edge["relation"], 0) + 1
        return {
            "schema": "atlas_zero.project_topology.rc2",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "layers": {
                node_type: sorted(node_ids)
                for node_type, node_ids in sorted(by_type.items())
            },
            "relation_counts": dict(sorted(relation_counts.items())),
        }

    def _build_statistics(
        self,
        *,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        modules: list[dict[str, Any]],
        name_to_nodes: dict[str, list[str]],
        exclusions: list[dict[str, Any]],
        unresolved_imports: list[dict[str, Any]],
        similarity_count: int,
    ) -> dict[str, Any]:
        node_types: dict[str, int] = {}
        node_states: dict[str, int] = {}
        edge_types: dict[str, int] = {}
        for node in nodes:
            node_types[node["type"]] = node_types.get(node["type"], 0) + 1
            for state in node.get("state", []):
                node_states[state] = node_states.get(state, 0) + 1
        for edge in edges:
            edge_types[edge["relation"]] = edge_types.get(edge["relation"], 0) + 1

        unique_logical_names = len(name_to_nodes)
        duplicate_logical_names = sum(
            1 for node_ids in name_to_nodes.values() if len(node_ids) > 1
        )
        unnamed_modules = sum(
            1 for module in modules if not str(module.get("module", "")).strip()
        )
        syntax_errors = sum(not bool(module.get("syntax_ok", True)) for module in modules)

        return {
            "schema": "atlas_zero.graph_statistics.rc2",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_module_records": len(modules),
            "represented_module_nodes": node_types.get("module", 0),
            "unique_logical_module_names": unique_logical_names,
            "duplicate_logical_module_names": duplicate_logical_names,
            "unnamed_module_records": unnamed_modules,
            "syntax_error_module_records": syntax_errors,
            "module_coverage_percent": round(
                100.0 * node_types.get("module", 0) / max(1, len(modules)),
                2,
            ),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_types": dict(sorted(node_types.items())),
            "node_states": dict(sorted(node_states.items())),
            "edge_types": dict(sorted(edge_types.items())),
            "participation_explanations": len(exclusions),
            "unresolved_internal_imports": len(unresolved_imports),
            "similarity_edges": similarity_count,
            "coverage_status": (
                "complete"
                if node_types.get("module", 0) == len(modules)
                else "incomplete"
            ),
        }

    def _edge(
        self,
        *,
        source: str,
        target: str,
        relation: str,
        evidence: str,
        confidence: float,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        identity = f"{source}|{relation}|{target}|{evidence}|{metadata or {}}"
        return {
            "id": stable_node_id("edge", identity),
            "source": source,
            "target": target,
            "relation": relation,
            "evidence": evidence,
            "confidence": round(max(0.0, min(1.0, confidence)), 4),
            "metadata": metadata or {},
        }

    def _markdown_report(
        self,
        *,
        summary: dict[str, Any],
        statistics: dict[str, Any],
        topology: dict[str, Any],
        knowledge_paths: dict[str, Any],
        similarity_payload: dict[str, Any],
        exclusions: list[dict[str, Any]],
        unresolved_imports: list[dict[str, Any]],
        system_registry: dict[str, Any],
    ) -> str:
        lines = [
            "# ATLAS ZERO RC2 — Project Knowledge Graph",
            "",
            f"- Registry version: `{REGISTRY_VERSION}`",
            f"- Generated at: `{summary['generated_at']}`",
            f"- Project root: `{summary['project_root']}`",
            "",
            "## Coverage",
            "",
            f"- Source module records: **{statistics['source_module_records']}**",
            f"- Represented module nodes: **{statistics['represented_module_nodes']}**",
            f"- Module coverage: **{statistics['module_coverage_percent']}%**",
            f"- Coverage status: **{statistics['coverage_status']}**",
            f"- Unique logical module names: **{statistics['unique_logical_module_names']}**",
            f"- Duplicate logical module names: **{statistics['duplicate_logical_module_names']}**",
            f"- Unnamed module records: **{statistics['unnamed_module_records']}**",
            f"- Syntax-error module records: **{statistics['syntax_error_module_records']}**",
            "",
            "## Graph",
            "",
            f"- Nodes: **{statistics['node_count']}**",
            f"- Edges: **{statistics['edge_count']}**",
            f"- Knowledge paths: **{knowledge_paths['count']}**",
            f"- Similarity candidates: **{similarity_payload['candidate_count']}**",
            f"- Unresolved internal imports: **{statistics['unresolved_internal_imports']}**",
            "",
            "## Node types",
            "",
        ]
        for node_type, count in statistics["node_types"].items():
            lines.append(f"- `{node_type}`: **{count}**")

        lines += ["", "## Edge types", ""]
        for relation, count in statistics["edge_types"].items():
            lines.append(f"- `{relation}`: **{count}**")

        lines += ["", "## Module states", ""]
        for state, count in statistics["node_states"].items():
            lines.append(f"- `{state}`: **{count}**")

        lines += ["", "## Top knowledge paths", ""]
        if knowledge_paths["paths"]:
            for path in knowledge_paths["paths"][:30]:
                lines.append(f"- {path['display']}")
        else:
            lines.append("- No multi-node paths detected.")

        lines += ["", "## Highest similarity candidates", ""]
        if similarity_payload["candidates"]:
            for item in similarity_payload["candidates"][:40]:
                lines.append(
                    f"- `{item['left_path']}` ↔ `{item['right_path']}` — "
                    f"**{item['similarity_score']}%** ({item['confidence']})"
                )
        else:
            lines.append("- None detected above the configured threshold.")

        lines += ["", "## Participation explanations", ""]
        if exclusions:
            for item in exclusions[:100]:
                reasons = ", ".join(item["reasons"])
                lines.append(
                    f"- `{item['path']}` — `{item['graph_participation']}`: {reasons}"
                )
        else:
            lines.append("- Every module has unambiguous full participation.")

        lines += ["", "## Unresolved imports", ""]
        if unresolved_imports:
            for item in unresolved_imports[:100]:
                lines.append(
                    f"- `{item['source']}` → `{item['target']}` — {item['reason']}"
                )
        else:
            lines.append("- None.")

        lines += [
            "",
            "## Important note",
            "",
            "All source module records are retained as graph nodes, including syntax-error, "
            "archive, tool, test, orphan and duplicate-name files. Ambiguous import edges "
            "are preserved with reduced confidence instead of silently dropping modules.",
            "",
            f"System Registry reported **{system_registry.get('summary', {}).get('module_count', 0)}** "
            "module records at graph build time.",
            "",
        ]
        return "\n".join(lines)

class SystemHealthRC2:
    """Create a compact health report from existing registry outputs."""

    def __init__(self, project_root: Path | str, output_dir: Path | str | None = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.output_dir = (
            Path(output_dir).resolve()
            if output_dir is not None
            else self.project_root / "workspace" / "system"
        )

    def build(self) -> dict[str, Any]:
        system = load_json_object(self.output_dir / "system_registry.json")
        dependency = load_json_object(self.output_dir / "dependency_intelligence.json")
        generated_at = datetime.now(timezone.utc).isoformat()
        syntax_errors = int(system.get("summary", {}).get("syntax_errors", 0))
        layer_violations = int(
            dependency.get("summary", {}).get("layer_violations", 0)
        )
        architecture_score = float(
            dependency.get("summary", {}).get("architecture_score", 0.0)
        )
        status = "healthy"
        if syntax_errors > 0 or architecture_score < 70:
            status = "attention"
        if architecture_score < 50 or syntax_errors >= 25:
            status = "critical"

        payload = {
            "schema": "atlas_zero.system_health.rc2",
            "generated_at": generated_at,
            "status": status,
            "architecture_score": architecture_score,
            "syntax_errors": syntax_errors,
            "scan_problems": int(system.get("summary", {}).get("scan_problems", 0)),
            "layer_violations": layer_violations,
            "critical_nodes": int(
                dependency.get("summary", {}).get("critical_nodes", 0)
            ),
            "dead_modules": int(
                dependency.get("summary", {}).get("dead_modules", 0)
            ),
        }
        json_dump(self.output_dir / "system_health.json", payload)
        return payload

def locate_project_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        score = sum((candidate / marker).exists() for marker in (".git", "pyproject.toml", "src"))
        if score >= 2 or (candidate / ".git").exists():
            return candidate
    return current




def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "ATLAS ZERO RC2 system registry, dependency intelligence "
            "and project knowledge graph."
        )
    )
    parser.add_argument(
        "--mode",
        choices=(
            "registry",
            "dependency",
            "knowledge",
            "graph",
            "architecture",
            "health",
            "all",
        ),
        default="registry",
        help=(
            "registry: scan source; dependency: analyze registries; "
            "knowledge/graph: build the Project Knowledge Graph; "
            "architecture: run registry, dependency and knowledge graph; "
            "health: run the complete diagnostic chain and health report; "
            "all: run registry, dependency and knowledge graph."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root; default is auto-detected.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory; default is <root>/workspace/system.",
    )
    parser.add_argument(
        "--tracked-only",
        action="store_true",
        help="Scan only Python files tracked by Git.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Additional directory name to exclude; may be repeated.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Rebuild all prerequisite registries before the selected stage.",
    )
    return parser.parse_args(argv)


def print_registry_summary(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print("\n" + "=" * 72)
    print("ATLAS ZERO RC2 — SYSTEM REGISTRY COMPLETE")
    print("=" * 72)
    print(f"Project root:      {result['project_root']}")
    print(f"Output directory:  {result['output_dir']}")
    print(f"Python modules:    {summary['module_count']}")
    print(f"Python lines:      {summary['total_lines']}")
    print(f"Classes:           {summary['class_count']}")
    print(f"Syntax errors:     {summary['syntax_errors']}")
    print(f"Artifacts:         {summary['unique_artifacts']}")
    print(f"Dependency cycles: {summary['dependency_cycles']}")
    print(f"Scan problems:     {summary['scan_problems']}")
    print("=" * 72)


def print_dependency_summary(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print("\n" + "=" * 72)
    print("ATLAS ZERO RC2 — DEPENDENCY INTELLIGENCE COMPLETE")
    print("=" * 72)
    print(f"Project root:       {result['project_root']}")
    print(f"Output directory:   {result['output_dir']}")
    print(f"Modules:            {summary['module_count']}")
    print(f"Internal edges:     {summary['internal_edges']}")
    print(f"Critical nodes:     {summary['critical_nodes']}")
    print(f"Dead candidates:    {summary['dead_modules']}")
    print(f"Isolated modules:   {summary['isolated_modules']}")
    print(f"Layer violations:   {summary['layer_violations']}")
    print(f"Director chains:    {summary['director_chains']}")
    print(f"Duplicate groups:   {summary['duplicate_candidates']}")
    print(
        f"Architecture score: {summary['architecture_score']} "
        f"({summary['architecture_grade']})"
    )
    print("=" * 72)


def print_knowledge_summary(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print("\n" + "=" * 72)
    print("ATLAS ZERO RC2 — PROJECT KNOWLEDGE GRAPH COMPLETE")
    print("=" * 72)
    print(f"Project root:        {result['project_root']}")
    print(f"Output directory:    {result['output_dir']}")
    print(f"Source modules:      {summary['source_module_records']}")
    print(f"Module nodes:        {summary['represented_module_nodes']}")
    print(f"Module coverage:     {summary['module_coverage_percent']}%")
    print(f"Unique module names: {summary['unique_logical_module_names']}")
    print(f"Duplicate names:     {summary['duplicate_logical_module_names']}")
    print(f"Syntax-error nodes:  {summary['syntax_error_module_records']}")
    print(f"Total graph nodes:   {summary['node_count']}")
    print(f"Total graph edges:   {summary['edge_count']}")
    print(f"Similarity edges:    {summary['similarity_edges']}")
    print(f"Unresolved imports:  {summary['unresolved_internal_imports']}")
    print(f"Coverage status:     {summary['coverage_status']}")
    print("=" * 72)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve() if args.root else locate_project_root(Path.cwd())
    output = (
        args.output.resolve()
        if args.output is not None
        else root / "workspace" / "system"
    )

    try:
        full_chain_modes = {"architecture", "health", "all"}
        knowledge_modes = {"knowledge", "graph", *full_chain_modes}
        dependency_modes = {"dependency", *knowledge_modes}

        registry_required_files = (
            output / "system_registry.json",
            output / "module_registry.json",
            output / "class_registry.json",
            output / "runtime_registry.json",
            output / "artifact_registry.json",
            output / "dependency_registry.json",
        )
        dependency_required_files = (
            output / "dependency_intelligence.json",
            output / "dependency_heatmap.json",
            output / "critical_nodes.json",
        )

        should_build_registry = (
            args.mode == "registry"
            or args.mode in full_chain_modes
            or args.refresh
            or any(not path.exists() for path in registry_required_files)
        )
        if should_build_registry:
            registry_result = SystemRegistryRC2(
                root,
                output,
                include_untracked=not args.tracked_only,
                excluded_dirs=set(args.exclude),
            ).build()
            print_registry_summary(registry_result)

        should_build_dependency = (
            args.mode in dependency_modes
            and (
                args.mode == "dependency"
                or args.mode in full_chain_modes
                or args.refresh
                or any(not path.exists() for path in dependency_required_files)
            )
        )
        if should_build_dependency:
            dependency_result = DependencyIntelligenceRC2(root, output).build()
            print_dependency_summary(dependency_result)

        if args.mode in knowledge_modes:
            knowledge_result = ProjectKnowledgeGraphRC2(root, output).build()
            print_knowledge_summary(knowledge_result)

        if args.mode == "health":
            health = SystemHealthRC2(root, output).build()
            print("\n" + "=" * 72)
            print("ATLAS ZERO RC2 — SYSTEM HEALTH COMPLETE")
            print("=" * 72)
            print(f"Status:             {health['status']}")
            print(f"Architecture score: {health['architecture_score']}")
            print(f"Syntax errors:      {health['syntax_errors']}")
            print(f"Layer violations:   {health['layer_violations']}")
            print(f"Critical nodes:     {health['critical_nodes']}")
            print("=" * 72)

    except KeyboardInterrupt:
        print("[SystemRegistryRC2] interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(
            f"[SystemRegistryRC2] fatal error: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
