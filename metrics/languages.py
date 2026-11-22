"""File classification: which language a path is written in, and which paths
are not hand-written work (lockfiles, vendored code, generated output, data).

Colors are GitHub linguist's, so the languages bar matches what GitHub shows.
"""

from __future__ import annotations

import fnmatch
import posixpath

# name -> color
COLORS = {
    "Assembly": "#6E4C13", "Batchfile": "#C1F12E", "C": "#555555", "C#": "#178600",
    "C++": "#f34b7d", "Clojure": "#db5855", "CMake": "#DA3434", "CSS": "#663399",
    "Cuda": "#3A4E3A", "Dart": "#00B4AB", "Dockerfile": "#384d54", "Elixir": "#6e4a7e",
    "Elm": "#60B5CC", "Emacs Lisp": "#c065db", "Erlang": "#B83998", "F#": "#b845fc",
    "Fortran": "#4d41b1", "GLSL": "#5686a5", "Go": "#00ADD8", "Groovy": "#4298b8",
    "Haskell": "#5e5086", "HCL": "#844FBA", "HTML": "#e34c26", "Java": "#b07219",
    "JavaScript": "#f1e05a", "Julia": "#a270ba", "Jupyter Notebook": "#DA5B0B",
    "Kotlin": "#A97BFF", "Less": "#1d365d", "Lua": "#000080", "Makefile": "#427819",
    "MATLAB": "#e16737", "Nim": "#ffc200", "Nix": "#7e7eff", "Objective-C": "#438eff",
    "OCaml": "#ef7a08", "Perl": "#0298c3", "PHP": "#4F5D95", "PowerShell": "#012456",
    "Prolog": "#74283c", "Python": "#3572A5", "R": "#198CE7", "Racket": "#3c5caa",
    "Ruby": "#701516", "Rust": "#dea584", "Sass": "#a53b70", "Scala": "#c22d40",
    "Scheme": "#1e4aec", "SCSS": "#c6538c", "Shell": "#89e051", "Solidity": "#AA6746",
    "SQL": "#e38c00", "Svelte": "#ff3e00", "Swift": "#F05138", "SystemVerilog": "#DAE1C2",
    "TeX": "#3D6117", "TypeScript": "#3178c6", "Verilog": "#b2b7f8", "VHDL": "#adb2cb",
    "Vim Script": "#199f4b", "Vue": "#41b883", "Zig": "#ec915c", "Astro": "#ff5a03",
}

EXTENSIONS = {
    "asm": "Assembly", "s": "Assembly", "bat": "Batchfile", "cmd": "Batchfile",
    "c": "C", "h": "C", "cs": "C#", "cpp": "C++", "cc": "C++", "cxx": "C++", "c++": "C++",
    "hpp": "C++", "hh": "C++", "hxx": "C++", "ino": "C++", "clj": "Clojure", "cljs": "Clojure",
    "cljc": "Clojure", "cmake": "CMake", "css": "CSS", "cu": "Cuda", "cuh": "Cuda",
    "dart": "Dart", "ex": "Elixir", "exs": "Elixir", "elm": "Elm", "el": "Emacs Lisp",
    "erl": "Erlang", "hrl": "Erlang", "fs": "F#", "fsx": "F#", "f90": "Fortran", "f95": "Fortran",
    "f": "Fortran", "glsl": "GLSL", "frag": "GLSL", "vert": "GLSL", "go": "Go",
    "groovy": "Groovy", "gradle": "Groovy", "hs": "Haskell", "tf": "HCL", "hcl": "HCL",
    "html": "HTML", "htm": "HTML", "java": "Java", "js": "JavaScript", "jsx": "JavaScript",
    "mjs": "JavaScript", "cjs": "JavaScript", "jl": "Julia", "ipynb": "Jupyter Notebook",
    "kt": "Kotlin", "kts": "Kotlin", "less": "Less", "lua": "Lua", "mk": "Makefile",
    "nim": "Nim", "nix": "Nix", "m": "Objective-C", "mm": "Objective-C", "ml": "OCaml",
    "mli": "OCaml", "pl": "Perl", "pm": "Perl", "php": "PHP", "ps1": "PowerShell",
    "psm1": "PowerShell", "pro": "Prolog", "py": "Python", "pyw": "Python", "pyi": "Python",
    "pyx": "Python", "r": "R", "rkt": "Racket", "rb": "Ruby", "rs": "Rust", "sass": "Sass",
    "scala": "Scala", "sc": "Scala", "scm": "Scheme", "ss": "Scheme", "scss": "SCSS",
    "sh": "Shell", "bash": "Shell", "zsh": "Shell", "fish": "Shell", "sol": "Solidity",
    "sql": "SQL", "svelte": "Svelte", "swift": "Swift", "sv": "SystemVerilog",
    "svh": "SystemVerilog", "tex": "TeX", "sty": "TeX", "ts": "TypeScript", "tsx": "TypeScript",
    "mts": "TypeScript", "cts": "TypeScript", "v": "Verilog", "vh": "Verilog", "vhd": "VHDL",
    "vhdl": "VHDL", "vim": "Vim Script", "vue": "Vue", "zig": "Zig", "astro": "Astro",
}

FILENAMES = {
    "makefile": "Makefile", "gnumakefile": "Makefile", "dockerfile": "Dockerfile",
    "cmakelists.txt": "CMake", "vimrc": "Vim Script", ".vimrc": "Vim Script",
    ".bashrc": "Shell", ".zshrc": "Shell", "rakefile": "Ruby", "gemfile": "Ruby",
}

# Directories whose contents are third-party, build output or tooling state.
DEFAULT_EXCLUDE_DIRS = {
    "node_modules", "bower_components", "jspm_packages", "vendor", "vendors", "third_party",
    "third-party", "thirdparty", "external", "dist", "build", "out", "target", "obj", ".next", ".nuxt", ".svelte-kit", ".turbo", ".parcel-cache", ".cache", "coverage",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".tox", ".venv", "venv", "env",
    "site-packages", ".gradle", ".idea", ".vscode", ".vs", "pods", "deriveddata", "carthage",
    ".terraform", "cmake-build-debug", "cmake-build-release", ".ipynb_checkpoints",
}

# Directory sequences that hold generated documentation (Javadoc, Sphinx, coverage).
DEFAULT_EXCLUDE_DIR_PATHS = ["docs/api", "doc/api", "javadoc", "apidocs", "_build", "htmlcov"]

# Basename globs (case-insensitive) for files that aren't hand-written code.
DEFAULT_EXCLUDE_FILES = [
    # lockfiles
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock",
    "bun.lockb", "poetry.lock", "pipfile.lock", "pdm.lock", "uv.lock", "cargo.lock",
    "gemfile.lock", "composer.lock", "go.sum", "flake.lock", "podfile.lock", "pubspec.lock",
    "mix.lock", "packages.lock.json", "*.lock",
    # generated / minified
    "*.min.js", "*.min.css", "*.min.mjs", "*.map", "*.bundle.js", "*.chunk.js", "*.pb.go",
    "*_pb2.py", "*_pb2_grpc.py", "*.pb.cc", "*.pb.h", "*.generated.*", "*.g.dart",
    "*.designer.cs",
    # data, logs and notebooks (notebook line counts are mostly JSON and cell output)
    "*.csv", "*.tsv", "*.psv", "*.jsonl", "*.ndjson", "*.geojson", "*.txt", "*.log", "*.dat",
    "*.out", "*.arff", "*.svg", "*.ipynb", "*.pdf", "*.drawio",
    # boilerplate
    ".gitignore", ".gitattributes", ".gitmodules", ".dockerignore", ".npmignore",
    ".prettierignore", ".eslintignore", "license", "license.*", "licence", "licence.*",
    "copying", "copying.*", ".ds_store", "thumbs.db",
]

# Plain-text files that are code despite their .txt extension.
_TXT_CODE = {"cmakelists.txt"}


class PathFilter:
    def __init__(self, exclude_dirs=(), exclude_files=(), exclude_paths=(), defaults=True):
        self.dirs = {d.lower() for d in exclude_dirs}
        self.files = [f.lower() for f in exclude_files]
        self.paths = list(exclude_paths)
        self.dir_paths: list[str] = []
        if defaults:
            self.dirs |= DEFAULT_EXCLUDE_DIRS
            self.files += DEFAULT_EXCLUDE_FILES
            self.dir_paths = [f"/{d}/" for d in DEFAULT_EXCLUDE_DIR_PATHS]

    def excluded(self, repo: str, path: str) -> bool:
        parts = path.lower().split("/")
        base = parts[-1]
        if any(p in self.dirs for p in parts[:-1]):
            return True
        if any(d in "/" + path.lower() for d in self.dir_paths):
            return True
        if base not in _TXT_CODE and any(fnmatch.fnmatchcase(base, g) for g in self.files):
            return True
        full = f"{repo}/{path}"
        return any(fnmatch.fnmatch(full, g) for g in self.paths)


def language_of(path: str) -> str | None:
    base = posixpath.basename(path).lower()
    if base in FILENAMES:
        return FILENAMES[base]
    _, ext = posixpath.splitext(base)
    return EXTENSIONS.get(ext[1:]) if ext else None


def color_of(language: str) -> str:
    return COLORS.get(language, "#8b949e")
