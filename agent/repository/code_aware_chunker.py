import re
import ast
from typing import List, Optional, Set
from langchain_text_splitters import RecursiveCharacterTextSplitter
from agent.repository.models import CodeChunk, RepositoryFile
from agent.repository.file_hash import generate_file_hash


# Files with <= this many lines get a whole-file chunk in addition to structural chunks
WHOLE_FILE_THRESHOLD = 80


class CodeAwareChunker:
    """Code-aware chunking for different programming languages."""

    def __init__(self, chunk_size: int = 1500, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.fallback_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def chunk_file(self, file: RepositoryFile) -> List[CodeChunk]:
        """Chunk a file based on its language using code-aware strategies."""
        language = file.language.lower()

        if language == "python":
            chunks = self._chunk_python(file)
        elif language in ["javascript", "typescript"]:
            chunks = self._chunk_js_ts(file)
        elif language == "markdown":
            chunks = self._chunk_markdown(file)
        elif language == "html":
            chunks = self._chunk_html(file)
        elif language == "css":
            chunks = self._chunk_css(file)
        elif language == "json":
            chunks = self._chunk_json(file)
        else:
            chunks = self._chunk_generic(file)

        # For small files, always add a whole-file chunk so nothing slips through
        line_count = file.content.count("\n") + 1
        if line_count <= WHOLE_FILE_THRESHOLD:
            file_hash = generate_file_hash(file.content)
            whole_chunk = CodeChunk(
                chunk_id=f"{file.path}:whole_file",
                file_path=file.path,
                language=file.language,
                chunk_type="whole_file",
                start_line=1,
                end_line=line_count,
                content=file.content,
                file_hash=file_hash,
            )
            # Prepend so it's retrieved first
            chunks = [whole_chunk] + chunks

        # Deduplicate by chunk_id while preserving order
        seen: Set[str] = set()
        unique_chunks = []
        for chunk in chunks:
            if chunk.chunk_id not in seen:
                seen.add(chunk.chunk_id)
                unique_chunks.append(chunk)

        return unique_chunks

    # ─── Python ────────────────────────────────────────────────────────────────

    def _chunk_python(self, file: RepositoryFile) -> List[CodeChunk]:
        """Python-specific chunking using AST parsing."""
        chunks: List[CodeChunk] = []
        lines = file.content.splitlines()
        file_hash = generate_file_hash(file.content)

        try:
            tree = ast.parse(file.content)
        except (SyntaxError, ValueError):
            return self._chunk_generic(file)

        # 1. Imports — collect all import nodes and emit a single chunk
        import_lines: List[str] = []
        import_start: Optional[int] = None
        import_end: int = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                s = node.lineno - 1
                e = (node.end_lineno or node.lineno) - 1
                if import_start is None:
                    import_start = s
                import_end = e
                import_lines.extend(lines[s : e + 1])

        if import_lines and import_start is not None:
            chunks.append(
                CodeChunk(
                    chunk_id=f"{file.path}:imports",
                    file_path=file.path,
                    language=file.language,
                    chunk_type="import",
                    start_line=import_start + 1,
                    end_line=import_end + 1,
                    content="\n".join(import_lines),
                    file_hash=file_hash,
                )
            )

        # Determine which lines belong to class/function bodies (to find module-level code)
        class_and_func_line_ranges: List[tuple] = []

        # 2. Top-level classes (full body as one chunk)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                start = node.lineno - 1
                end = (node.end_lineno or node.lineno) - 1
                class_and_func_line_ranges.append((start, end))
                chunks.append(
                    CodeChunk(
                        chunk_id=f"{file.path}:class:{node.name}",
                        file_path=file.path,
                        language=file.language,
                        chunk_type="class",
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        content="\n".join(lines[start : end + 1]),
                        class_name=node.name,
                        file_hash=file_hash,
                    )
                )

        # 3. Top-level functions only (not methods inside classes)
        top_level_class_names = {
            n.name for n in tree.body if isinstance(n, ast.ClassDef)
        }
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno - 1
                end = (node.end_lineno or node.lineno) - 1
                class_and_func_line_ranges.append((start, end))
                chunks.append(
                    CodeChunk(
                        chunk_id=f"{file.path}:function:{node.name}",
                        file_path=file.path,
                        language=file.language,
                        chunk_type="function",
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        content="\n".join(lines[start : end + 1]),
                        function_name=node.name,
                        file_hash=file_hash,
                    )
                )

        # 4. Module-level constants / assignments (e.g. CONFIG = {...}, X = 42)
        module_level_lines: List[str] = []
        module_start: Optional[int] = None
        module_end: int = 0

        covered = set()
        for s, e in class_and_func_line_ranges:
            for i in range(s, e + 1):
                covered.add(i)

        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                s = node.lineno - 1
                e = (node.end_lineno or node.lineno) - 1
                if s not in covered:
                    if module_start is None:
                        module_start = s
                    module_end = e
                    module_level_lines.extend(lines[s : e + 1])

        if module_level_lines and module_start is not None:
            chunks.append(
                CodeChunk(
                    chunk_id=f"{file.path}:module_constants",
                    file_path=file.path,
                    language=file.language,
                    chunk_type="module",
                    start_line=module_start + 1,
                    end_line=module_end + 1,
                    content="\n".join(module_level_lines),
                    file_hash=file_hash,
                )
            )

        return chunks if chunks else self._chunk_generic(file)

    # ─── JavaScript / TypeScript ────────────────────────────────────────────────

    def _chunk_js_ts(self, file: RepositoryFile) -> List[CodeChunk]:
        """JavaScript/TypeScript chunking with full body extraction via brace matching."""
        chunks: List[CodeChunk] = []
        lines = file.content.splitlines()
        file_hash = generate_file_hash(file.content)

        # 1. Imports (ES6 and CommonJS)
        import_lines: List[str] = []
        import_start: Optional[int] = None
        import_pattern = re.compile(
            r"^(import\s.+?from\s+[\"']|import\s*[\"']|const\s+\w+\s*=\s*require\s*\(|"
            r"const\s*\{[^}]+\}\s*=\s*require\s*\()",
            re.MULTILINE,
        )
        for i, line in enumerate(lines):
            if import_pattern.match(line.strip()):
                if import_start is None:
                    import_start = i
                import_lines.append(line)

        if import_lines and import_start is not None:
            chunks.append(
                CodeChunk(
                    chunk_id=f"{file.path}:imports",
                    file_path=file.path,
                    language=file.language,
                    chunk_type="import",
                    start_line=import_start + 1,
                    end_line=import_start + len(import_lines),
                    content="\n".join(import_lines),
                    file_hash=file_hash,
                )
            )

        # 2. Module-level constants/variables (not inside functions/classes)
        const_pattern = re.compile(
            r"^(?:const|let|var)\s+(\w+)\s*=\s*(?!(?:async\s*)?\(?[\w,\s]*\)?\s*=>|function)",
            re.MULTILINE,
        )
        for match in const_pattern.finditer(file.content):
            line_no = file.content[: match.start()].count("\n")
            # Only include if line doesn't look like an arrow function or class
            line_content = lines[line_no] if line_no < len(lines) else ""
            # Collect the whole statement until semicolon or next blank line
            stmt_lines = self._collect_statement_lines(lines, line_no)
            var_name = match.group(1)
            chunks.append(
                CodeChunk(
                    chunk_id=f"{file.path}:const:{var_name}",
                    file_path=file.path,
                    language=file.language,
                    chunk_type="constant",
                    start_line=line_no + 1,
                    end_line=line_no + len(stmt_lines),
                    content="\n".join(stmt_lines),
                    function_name=var_name,
                    file_hash=file_hash,
                )
            )

        # 3. Named functions (function keyword)
        func_decl_pattern = re.compile(
            r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+(\w+)\s*\(",
            re.MULTILINE,
        )
        for match in func_decl_pattern.finditer(file.content):
            func_name = match.group(1)
            line_no = file.content[: match.start()].count("\n")
            body_lines, end_line_no = self._extract_js_block(lines, line_no)
            if body_lines:
                chunks.append(
                    CodeChunk(
                        chunk_id=f"{file.path}:function:{func_name}",
                        file_path=file.path,
                        language=file.language,
                        chunk_type="function",
                        start_line=line_no + 1,
                        end_line=end_line_no + 1,
                        content="\n".join(body_lines),
                        function_name=func_name,
                        file_hash=file_hash,
                    )
                )

        # 4. Arrow functions assigned to const/let/var  (const foo = () => {...})
        arrow_pattern = re.compile(
            r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(",
            re.MULTILINE,
        )
        for match in arrow_pattern.finditer(file.content):
            func_name = match.group(1)
            line_no = file.content[: match.start()].count("\n")
            body_lines, end_line_no = self._extract_js_block(lines, line_no)
            if body_lines:
                chunks.append(
                    CodeChunk(
                        chunk_id=f"{file.path}:arrow:{func_name}",
                        file_path=file.path,
                        language=file.language,
                        chunk_type="function",
                        start_line=line_no + 1,
                        end_line=end_line_no + 1,
                        content="\n".join(body_lines),
                        function_name=func_name,
                        file_hash=file_hash,
                    )
                )

        # 5. Classes
        class_pattern = re.compile(
            r"^(?:export\s+(?:default\s+)?)?class\s+(\w+)", re.MULTILINE
        )
        for match in class_pattern.finditer(file.content):
            class_name = match.group(1)
            line_no = file.content[: match.start()].count("\n")
            body_lines, end_line_no = self._extract_js_block(lines, line_no)
            if body_lines:
                chunks.append(
                    CodeChunk(
                        chunk_id=f"{file.path}:class:{class_name}",
                        file_path=file.path,
                        language=file.language,
                        chunk_type="class",
                        start_line=line_no + 1,
                        end_line=end_line_no + 1,
                        content="\n".join(body_lines),
                        class_name=class_name,
                        file_hash=file_hash,
                    )
                )

        return chunks if chunks else self._chunk_generic(file)

    def _extract_js_block(
        self, lines: List[str], start_line: int
    ) -> tuple[List[str], int]:
        """Extract a JS block starting at start_line by matching braces.
        Returns (lines_of_block, end_line_index).
        """
        depth = 0
        found_open = False
        result_lines = []

        for i in range(start_line, len(lines)):
            line = lines[i]
            result_lines.append(line)
            for ch in line:
                if ch == "{":
                    depth += 1
                    found_open = True
                elif ch == "}":
                    depth -= 1
            if found_open and depth == 0:
                return result_lines, i

        # No balanced block found — return everything from start_line to EOF
        return lines[start_line:], len(lines) - 1

    def _collect_statement_lines(
        self, lines: List[str], start: int, max_lines: int = 5
    ) -> List[str]:
        """Collect lines of a simple statement until ';' or blank line."""
        result = []
        for i in range(start, min(start + max_lines, len(lines))):
            result.append(lines[i])
            if lines[i].rstrip().endswith(";") or (i > start and not lines[i].strip()):
                break
        return result

    # ─── HTML ──────────────────────────────────────────────────────────────────

    def _chunk_html(self, file: RepositoryFile) -> List[CodeChunk]:
        """HTML chunking: head section, body sections, script/style blocks."""
        chunks: List[CodeChunk] = []
        file_hash = generate_file_hash(file.content)
        lines = file.content.splitlines()

        # Extract major sections: <head>, <body>, <script>, <style>
        section_pattern = re.compile(
            r"<(head|body|script|style|header|main|footer|section|article|nav)[\s>]",
            re.IGNORECASE,
        )
        close_pattern = re.compile(
            r"</(head|body|script|style|header|main|footer|section|article|nav)>",
            re.IGNORECASE,
        )

        open_stack: List[tuple] = []  # (tag, line_no)

        for i, line in enumerate(lines):
            for m in section_pattern.finditer(line):
                open_stack.append((m.group(1).lower(), i))

            for m in close_pattern.finditer(line):
                tag = m.group(1).lower()
                # Find matching open
                for j in range(len(open_stack) - 1, -1, -1):
                    if open_stack[j][0] == tag:
                        start_line = open_stack[j][1]
                        block = "\n".join(lines[start_line : i + 1])
                        if block.strip():
                            chunks.append(
                                CodeChunk(
                                    chunk_id=f"{file.path}:html:{tag}:{start_line}",
                                    file_path=file.path,
                                    language=file.language,
                                    chunk_type=tag,
                                    start_line=start_line + 1,
                                    end_line=i + 1,
                                    content=block,
                                    file_hash=file_hash,
                                )
                            )
                        open_stack.pop(j)
                        break

        return chunks if chunks else self._chunk_generic(file)

    # ─── CSS ───────────────────────────────────────────────────────────────────

    def _chunk_css(self, file: RepositoryFile) -> List[CodeChunk]:
        """CSS chunking: each rule block as a chunk."""
        chunks: List[CodeChunk] = []
        file_hash = generate_file_hash(file.content)
        lines = file.content.splitlines()

        # Match CSS rule blocks: selector { ... }
        rule_pattern = re.compile(r"([^{}@][^{]*)\{([^}]*)\}", re.DOTALL)
        at_rule_pattern = re.compile(r"(@\w+[^{]*)\{([^}]*)\}", re.DOTALL)

        def add_rule_chunks(pattern: re.Pattern, chunk_type: str) -> None:
            for match in pattern.finditer(file.content):
                selector = match.group(1).strip()
                if not selector:
                    continue
                start_line = file.content[: match.start()].count("\n")
                end_line = file.content[: match.end()].count("\n")
                safe_selector = re.sub(r"[^\w\s-]", "_", selector)[:40]
                chunks.append(
                    CodeChunk(
                        chunk_id=f"{file.path}:{chunk_type}:{safe_selector}:{start_line}",
                        file_path=file.path,
                        language=file.language,
                        chunk_type=chunk_type,
                        start_line=start_line + 1,
                        end_line=end_line + 1,
                        content=match.group(0).strip(),
                        function_name=selector,
                        file_hash=file_hash,
                    )
                )

        add_rule_chunks(at_rule_pattern, "at_rule")
        add_rule_chunks(rule_pattern, "css_rule")

        return chunks if chunks else self._chunk_generic(file)

    # ─── JSON ──────────────────────────────────────────────────────────────────

    def _chunk_json(self, file: RepositoryFile) -> List[CodeChunk]:
        """JSON chunking: top-level keys as separate chunks."""
        import json

        chunks: List[CodeChunk] = []
        file_hash = generate_file_hash(file.content)

        try:
            data = json.loads(file.content)
        except json.JSONDecodeError:
            return self._chunk_generic(file)

        if not isinstance(data, dict):
            return self._chunk_generic(file)

        for key, value in data.items():
            content = f'"{key}": {json.dumps(value, indent=2)}'
            chunks.append(
                CodeChunk(
                    chunk_id=f"{file.path}:json:{key}",
                    file_path=file.path,
                    language=file.language,
                    chunk_type="json_key",
                    start_line=1,
                    end_line=1,
                    content=content,
                    function_name=key,
                    file_hash=file_hash,
                )
            )

        return chunks if chunks else self._chunk_generic(file)

    # ─── Markdown ──────────────────────────────────────────────────────────────

    def _chunk_markdown(self, file: RepositoryFile) -> List[CodeChunk]:
        """Markdown chunking based on headings."""
        chunks: List[CodeChunk] = []
        file_hash = generate_file_hash(file.content)
        lines = file.content.splitlines()

        current_chunk: List[str] = []
        current_heading = "Introduction"
        start_line = 1

        for i, line in enumerate(lines, 1):
            if line.startswith("#"):
                if current_chunk:
                    chunks.append(
                        CodeChunk(
                            chunk_id=f"{file.path}:heading:{current_heading}",
                            file_path=file.path,
                            language=file.language,
                            chunk_type="heading",
                            start_line=start_line,
                            end_line=i - 1,
                            content="\n".join(current_chunk),
                            function_name=current_heading,
                            file_hash=file_hash,
                        )
                    )
                current_heading = line.lstrip("#").strip()
                current_chunk = [line]
                start_line = i
            else:
                current_chunk.append(line)

        if current_chunk:
            chunks.append(
                CodeChunk(
                    chunk_id=f"{file.path}:heading:{current_heading}",
                    file_path=file.path,
                    language=file.language,
                    chunk_type="heading",
                    start_line=start_line,
                    end_line=len(lines),
                    content="\n".join(current_chunk),
                    function_name=current_heading,
                    file_hash=file_hash,
                )
            )

        return chunks if chunks else self._chunk_generic(file)

    # ─── Generic fallback ──────────────────────────────────────────────────────

    def _chunk_generic(self, file: RepositoryFile) -> List[CodeChunk]:
        """Fallback generic chunking using RecursiveCharacterTextSplitter."""
        file_hash = generate_file_hash(file.content)
        text_chunks = self.fallback_splitter.split_text(file.content)

        return [
            CodeChunk(
                chunk_id=f"{file.path}:generic:{idx}",
                file_path=file.path,
                language=file.language,
                chunk_type="generic",
                start_line=0,
                end_line=0,
                content=chunk,
                file_hash=file_hash,
            )
            for idx, chunk in enumerate(text_chunks)
        ]


def chunk_repository(files: List[RepositoryFile]) -> List[CodeChunk]:
    """Chunk multiple files using code-aware chunking."""
    chunker = CodeAwareChunker()
    all_chunks: List[CodeChunk] = []

    for file in files:
        all_chunks.extend(chunker.chunk_file(file))

    return all_chunks
