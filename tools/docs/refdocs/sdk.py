"""docs/reference/python-sdk.md: the public API of the `sse` package, from its docstrings.

The modules are read with `ast`, not imported: importing `sse.project` asks the daemon for the
task, which only exists inside a task container. A module's public names are those in `__all__`,
or else those without a leading underscore; module variables are documented only when they have a
docstring (a string literal right after the assignment).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from .page import ROOT, PageError, code

PACKAGE = ROOT / "sdk" / "python" / "sse"

# Documented modules, in page order.
MODULES = [
    "sse",
    "sse.project",
    "sse.metadata",
    "sse.prompt",
    "sse.tools.bencher",
    "sse.tools.bash",
    "sse.grading",
    "sse.reference",
    "sse.helper",
    "sse.error",
    "sse.daemon",
    "sse.ai",
]
# Modules left out of the page, with the reason.
UNDOCUMENTED = {
    "sse.tools": "only imports sse.tools.bash and sse.tools.bencher",
    "sse.cheating": "deprecated alias of sse.reference",
}

# Longer signatures are shown one parameter per line.
SIGNATURE_WIDTH = 80

# Decorators that replace a function's return value with an instance of their argument.
RESULT_DECORATORS = {"wrap_result"}


def module_path(name: str) -> Path:
    parts = name.split(".")[1:]
    base = PACKAGE.joinpath(*parts)
    return base / "__init__.py" if base.is_dir() else base.with_suffix(".py")


def discovered_modules() -> list[str]:
    names = []
    for path in sorted(PACKAGE.rglob("*.py")):
        parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
        names.append(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
    return names


# ---------------------------------------------------------------------------
# Docstrings to Markdown
# ---------------------------------------------------------------------------

ROLE = re.compile(r":(?:func|class|meth|mod|attr|data|exc|obj):`(~?)([^`]+)`")
SECTION = re.compile(r"^(Args|Arguments|Parameters|Attributes|Raises|Returns|Yields|Example|Examples|Note|Usage):?:?$")
LIST_SECTIONS = {"Args", "Arguments", "Parameters", "Attributes", "Raises"}
SECTION_TITLES = {"Args": "Arguments"}
ENTRY = re.compile(r"^(\S[^:]*?):\s*(.*)$")


def inline(text: str) -> str:
    # `~a.b.C` shows as `C`, as in Sphinx.
    text = ROLE.sub(lambda m: f"`{m[2].rsplit('.', 1)[-1] if m[1] else m[2]}`", text)
    return re.sub(r"``([^`]+)``", r"`\1`", text)


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def docstring_markdown(doc: str) -> str:
    """Google-style docstring sections and reST literal blocks (`::`) as Markdown."""
    lines = doc.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        section = SECTION.match(stripped) if indent_of(line) == 0 else None
        if section or stripped.endswith("::"):
            # The block is every following line that is blank or indented deeper.
            j = i + 1
            block: list[str] = []
            while j < len(lines) and (not lines[j].strip() or indent_of(lines[j]) > indent_of(line)):
                block.append(lines[j])
                j += 1
            while block and not block[-1].strip():
                block.pop()
            while block and not block[0].strip():
                block.pop(0)
            depth = min((indent_of(b) for b in block if b.strip()), default=0)
            body = [b[depth:] for b in block]
            title = section[1] if section else stripped[:-2].rstrip()
            if section is None or title in {"Usage", "Example", "Examples"} and stripped.endswith("::"):
                if title:
                    out.append(inline(title) + ":")
                    out.append("")
                out += ["```python", *[b.rstrip() for b in body], "```"]
            elif title in LIST_SECTIONS:
                out += [f"**{SECTION_TITLES.get(title, title)}:**", ""]
                entries: list[list[str]] = []
                for b in body:
                    if b.strip() and indent_of(b) == 0:
                        entries.append([b.strip()])
                    elif entries and b.strip():
                        entries[-1].append(b.strip())
                for entry in entries:
                    head, *rest = entry
                    m = ENTRY.match(head)
                    text = " ".join([m[2], *rest] if m else [head, *rest]).strip()
                    out.append(f"- `{m[1]}`: {inline(text)}" if m else f"- {inline(text)}")
            else:
                out += [f"**{SECTION_TITLES.get(title, title)}:**", ""]
                out += [inline(" ".join(b.strip() for b in body if b.strip()))]
            out.append("")
            i = j
            continue
        out.append(inline(line))
        i += 1
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return escape_html(text)


def escape_html(text: str) -> str:
    """`<` outside code as an entity, so the site does not read it as a tag."""
    parts = re.split(r"(```.*?```|`[^`\n]+`)", text, flags=re.DOTALL)
    return "".join(p if i % 2 else p.replace("<", "&lt;") for i, p in enumerate(parts))


# ---------------------------------------------------------------------------
# Signatures
# ---------------------------------------------------------------------------


def annotation(node: ast.expr | None) -> str:
    return f": {ast.unparse(node)}" if node is not None else ""


def parameters(args: ast.arguments, *, skip_self: bool) -> list[str]:
    positional = [*args.posonlyargs, *args.args]
    defaults: list[ast.expr | None] = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    params: list[str] = []
    for index, (arg, default) in enumerate(zip(positional, defaults, strict=True)):
        if skip_self and index == 0:
            continue
        text = arg.arg + annotation(arg.annotation)
        if default is not None:
            text += (" = " if arg.annotation else "=") + ast.unparse(default)
        params.append(text)
        if args.posonlyargs and arg is args.posonlyargs[-1]:
            params.append("/")
    if args.vararg:
        params.append("*" + args.vararg.arg + annotation(args.vararg.annotation))
    elif args.kwonlyargs:
        params.append("*")
    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        text = arg.arg + annotation(arg.annotation)
        if default is not None:
            text += (" = " if arg.annotation else "=") + ast.unparse(default)
        params.append(text)
    if args.kwarg:
        params.append("**" + args.kwarg.arg + annotation(args.kwarg.annotation))
    return params


def call(head: str, params: list[str], tail: str = "") -> str:
    """`head(params)tail` on one line, or one parameter per line when that is too long to read."""
    line = f"{head}({', '.join(params)}){tail}"
    if len(line) <= SIGNATURE_WIDTH or not params:
        return line
    return f"{head}(\n" + "".join(f"    {p},\n" for p in params) + f"){tail}"


def returns(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    if node.returns is not None:
        return f" -> {ast.unparse(node.returns)}"
    for decorator in node.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id in RESULT_DECORATORS
            and decorator.args
        ):
            return f" -> {ast.unparse(decorator.args[0])}"
    return ""


def type_params(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    params = getattr(node, "type_params", [])
    return f"[{', '.join(ast.unparse(p) for p in params)}]" if params else ""


def function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef, name: str, *, method: bool) -> str:
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return call(f"{prefix}{name}{type_params(node)}", parameters(node.args, skip_self=method), returns(node))


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------


@dataclass
class Member:
    name: str
    node: ast.AST
    doc: str | None


def is_public(name: str) -> bool:
    return not name.startswith("_")


def declared_all(tree: ast.Module) -> list[str] | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            value = ast.literal_eval(node.value)
            return [str(v) for v in value]
    return None


def members(tree: ast.Module) -> list[Member]:
    """The module's own public classes, functions and documented variables, in source order."""
    exported = declared_all(tree)
    found: list[Member] = []
    body = tree.body
    for index, node in enumerate(body):
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            found.append(Member(node.name, node, ast.get_docstring(node)))
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            following = body[index + 1] if index + 1 < len(body) else None
            if (
                len(names) == 1
                and isinstance(following, ast.Expr)
                and isinstance(following.value, ast.Constant)
                and isinstance(following.value.value, str)
            ):
                found.append(Member(names[0], node, ast.get_docstring(ast.Module([following], []))))
    if exported is not None:
        return [m for m in found if m.name in exported]
    return [m for m in found if is_public(m.name)]


def decorator_names(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    names = []
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        names.append(ast.unparse(target))
    return names


def doc_block(doc: str | None, owner: str) -> str:
    if not doc:
        raise PageError(f"{owner} has no docstring; the Python SDK reference needs one")
    return docstring_markdown(doc)


def render_variable(member: Member, module: str) -> list[str]:
    node = member.node
    assert isinstance(node, ast.Assign | ast.AnnAssign)
    declaration = member.name + (annotation(node.annotation) if isinstance(node, ast.AnnAssign) else "")
    return [
        f"### `{member.name}`",
        "",
        f"```python\n{declaration}\n```",
        "",
        doc_block(member.doc, f"{module}.{member.name}"),
    ]


def render_function(member: Member, module: str) -> list[str]:
    node = member.node
    assert isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    return [
        f"### `{member.name}()`",
        "",
        f"```python\n{function_signature(node, member.name, method=False)}\n```",
        "",
        doc_block(member.doc, f"{module}.{member.name}"),
    ]


@dataclass
class Field:
    name: str
    type: str
    default: str | None
    doc: str


def dataclass_fields(node: ast.ClassDef) -> list[Field]:
    fields = []
    for index, item in enumerate(node.body):
        if not (isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)):
            continue
        following = node.body[index + 1] if index + 1 < len(node.body) else None
        doc = ""
        if isinstance(following, ast.Expr) and isinstance(following.value, ast.Constant):
            doc = " ".join(str(following.value.value).split())
        default = ast.unparse(item.value) if item.value is not None else None
        fields.append(Field(item.target.id, ast.unparse(item.annotation), default, doc))
    return fields


def render_class(member: Member, module: str) -> list[str]:
    node = member.node
    assert isinstance(node, ast.ClassDef)
    decorators = decorator_names(node)
    is_dataclass = "dataclass" in {d.split(".")[-1] for d in decorators}
    fields = dataclass_fields(node) if is_dataclass else []
    init = next((i for i in node.body if isinstance(i, ast.FunctionDef) and i.name == "__init__"), None)
    # Shown as a call, the way it is constructed: the dataclass fields or the parameters of __init__.
    if init is not None:
        params = parameters(init.args, skip_self=True)
    else:
        params = [f"{f.name}: {f.type}" + (f" = {f.default}" if f.default else "") for f in fields]
    header = "".join(f"@{d}\n" for d in decorators) + call(f"class {member.name}", params)
    lines = [
        f"### `class {member.name}`",
        "",
        f"```python\n{header}\n```",
        "",
    ]
    if node.bases:
        lines += ["Subclass of " + ", ".join(f"`{ast.unparse(b)}`" for b in node.bases) + ".", ""]
    lines.append(doc_block(member.doc, f"{module}.{member.name}"))
    public = [f for f in fields if is_public(f.name)]
    if public:
        lines += ["", "| Field | Type | Description |", "|---|---|---|"]
        lines += [f"| `{f.name}` | {code(f.type)} | {inline(f.doc)} |" for f in public]
    for item in node.body:
        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef) and is_public(item.name):
            owner = f"{module}.{member.name}.{item.name}"
            is_property = "property" in decorator_names(item)
            if is_property:
                signature = f"{item.name}{returns(item).replace(' -> ', ': ')}"
                heading = f"#### `{member.name}.{item.name}`"
            else:
                signature = function_signature(item, item.name, method=True)
                heading = f"#### `{member.name}.{item.name}()`"
            lines += ["", heading, "", f"```python\n{signature}\n```", "", doc_block(ast.get_docstring(item), owner)]
    return lines


def render_module(name: str) -> str:
    path = module_path(name)
    tree = ast.parse(path.read_text(), str(path))
    lines = [f"## `{name}`", "", doc_block(ast.get_docstring(tree), f"module {name}")]
    for member in members(tree):
        lines.append("")
        if isinstance(member.node, ast.ClassDef):
            lines += render_class(member, name)
        elif isinstance(member.node, ast.FunctionDef | ast.AsyncFunctionDef):
            lines += render_function(member, name)
        else:
            lines += render_variable(member, name)
    return "\n".join(lines)


def regions() -> dict[str, str]:
    unlisted = sorted(set(discovered_modules()) - set(MODULES) - set(UNDOCUMENTED))
    if unlisted:
        raise PageError(
            f"sse modules missing from the Python SDK reference: {', '.join(unlisted)}; add them to MODULES "
            "or UNDOCUMENTED in tools/docs/refdocs/sdk.py"
        )
    missing = sorted(m for m in [*MODULES, *UNDOCUMENTED] if not module_path(m).is_file())
    if missing:
        raise PageError(f"tools/docs/refdocs/sdk.py lists modules that do not exist: {', '.join(missing)}")
    index = "\n".join(f"- [`{m}`](#{m.replace('.', '-')})" for m in MODULES)
    return {"sdk modules": index, "sdk api": "\n\n".join(render_module(m) for m in MODULES)}
