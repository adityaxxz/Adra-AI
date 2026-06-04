import re
import ast
from typing import List, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
from agent.repository.models import CodeChunk, RepositoryFile
from agent.repository.file_hash import generate_file_hash


class CodeAwareChunker:
    """Code-aware chunking for different programming languages."""
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
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
            return self._chunk_python(file)
        elif language in ["javascript", "typescript"]:
            return self._chunk_js_ts(file)
        elif language == "markdown":
            return self._chunk_markdown(file)
        else:
            return self._chunk_generic(file)
    
    def _chunk_python(self, file: RepositoryFile) -> List[CodeChunk]:
        """Python-specific chunking using AST parsing."""
        chunks = []
        lines = file.content.split('\n')
        file_hash = generate_file_hash(file.content)
        
        try:
            tree = ast.parse(file.content)
            
            # Extract imports
            imports = self._extract_python_imports(tree, lines)
            if imports:
                chunks.append(CodeChunk(
                    chunk_id=f"{file.path}:imports",
                    file_path=file.path,
                    language=file.language,
                    chunk_type="import",
                    start_line=imports["start_line"],
                    end_line=imports["end_line"],
                    content=imports["content"],
                    file_hash=file_hash
                ))
            
            # Extract classes
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_lines = self._get_node_lines(node, lines)
                    chunks.append(CodeChunk(
                        chunk_id=f"{file.path}:class:{node.name}",
                        file_path=file.path,
                        language=file.language,
                        chunk_type="class",
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        content=class_lines,
                        class_name=node.name,
                        file_hash=file_hash
                    ))
            
            # Extract functions
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_lines = self._get_node_lines(node, lines)
                    chunks.append(CodeChunk(
                        chunk_id=f"{file.path}:function:{node.name}",
                        file_path=file.path,
                        language=file.language,
                        chunk_type="function",
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        content=func_lines,
                        function_name=node.name,
                        file_hash=file_hash
                    ))
            
            # Extract module-level code
            module_code = self._extract_module_level_code(tree, lines)
            if module_code:
                chunks.append(CodeChunk(
                    chunk_id=f"{file.path}:module",
                    file_path=file.path,
                    language=file.language,
                    chunk_type="module",
                    start_line=module_code["start_line"],
                    end_line=module_code["end_line"],
                    content=module_code["content"],
                    file_hash=file_hash
                ))
            
        except (SyntaxError, ValueError):
            # Fallback to generic chunking if AST parsing fails
            return self._chunk_generic(file)
        
        # Always return at least generic chunks if no code-aware chunks were created
        return chunks if chunks else self._chunk_generic(file)
    
    def _extract_python_imports(self, tree: ast.AST, lines: List[str]) -> Optional[dict]:
        """Extract import statements from Python AST."""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                start_line = node.lineno - 1
                end_line = node.end_lineno if hasattr(node, 'end_lineno') else node.lineno
                imports.extend(lines[start_line:end_line])
        
        if imports:
            content = '\n'.join(imports)
            return {
                "start_line": 1,
                "end_line": len(imports),
                "content": content
            }
        return None
    
    def _get_node_lines(self, node: ast.AST, lines: List[str]) -> str:
        """Extract source lines for an AST node."""
        start = node.lineno - 1
        end = node.end_lineno if hasattr(node, 'end_lineno') else node.lineno
        return '\n'.join(lines[start:end])
    
    def _extract_module_level_code(self, tree: ast.AST, lines: List[str]) -> Optional[dict]:
        """Extract module-level code (code not inside functions/classes)."""
        # This is simplified - in practice, you'd track which lines are inside functions/classes
        return None
    
    def _chunk_js_ts(self, file: RepositoryFile) -> List[CodeChunk]:
        """JavaScript/TypeScript chunking using regex-based parsing."""
        chunks = []
        lines = file.content.split('\n')
        file_hash = generate_file_hash(file.content)
        
        # Extract imports
        imports = []
        import_pattern = r'^(import\s+.*?from\s+["\'].*?["\']|require\(["\'].*?["\'])'
        for i, line in enumerate(lines):
            if re.match(import_pattern, line.strip()):
                imports.append(line)
        
        if imports:
            chunks.append(CodeChunk(
                chunk_id=f"{file.path}:imports",
                file_path=file.path,
                language=file.language,
                chunk_type="import",
                start_line=1,
                end_line=len(imports),
                content='\n'.join(imports),
                file_hash=file_hash
            ))
        
        # Extract classes
        class_pattern = r'(?:class\s+(\w+)|interface\s+(\w+)|type\s+(\w+))'
        for match in re.finditer(class_pattern, file.content, re.MULTILINE):
            class_name = match.group(1) or match.group(2) or match.group(3)
            if class_name:
                # Extract the class definition (simplified)
                start = file.content[:match.start()].count('\n') + 1
                chunks.append(CodeChunk(
                    chunk_id=f"{file.path}:class:{class_name}",
                    file_path=file.path,
                    language=file.language,
                    chunk_type="class",
                    start_line=start,
                    end_line=start + 10,  # Approximate
                    content=match.group(0),
                    class_name=class_name,
                    file_hash=file_hash
                ))
        
        # Extract functions
        function_pattern = r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(?\w*\'?\)?\s*=>)'
        for match in re.finditer(function_pattern, file.content, re.MULTILINE):
            func_name = match.group(1) or match.group(2)
            if func_name:
                start = file.content[:match.start()].count('\n') + 1
                chunks.append(CodeChunk(
                    chunk_id=f"{file.path}:function:{func_name}",
                    file_path=file.path,
                    language=file.language,
                    chunk_type="function",
                    start_line=start,
                    end_line=start + 10,  # Approximate
                    content=match.group(0),
                    function_name=func_name,
                    file_hash=file_hash
                ))
        
        # Extract components (React/Vue/Angular)
        component_pattern = r'(?:export\s+(?:default\s+)?(?:const|function|class)\s+(\w+Component|\w+))'
        for match in re.finditer(component_pattern, file.content, re.MULTILINE):
            component_name = match.group(1)
            start = file.content[:match.start()].count('\n') + 1
            chunks.append(CodeChunk(
                chunk_id=f"{file.path}:component:{component_name}",
                file_path=file.path,
                language=file.language,
                chunk_type="component",
                start_line=start,
                end_line=start + 10,  # Approximate
                content=match.group(0),
                function_name=component_name,
                file_hash=file_hash
            ))
        
        # Module-level code (remaining content)
        if not chunks:
            return self._chunk_generic(file)
        
        return chunks
    
    def _chunk_markdown(self, file: RepositoryFile) -> List[CodeChunk]:
        """Markdown chunking based on headings."""
        chunks = []
        file_hash = generate_file_hash(file.content)
        lines = file.content.split('\n')
        
        current_chunk = []
        current_heading = "Introduction"
        start_line = 1
        
        for i, line in enumerate(lines, 1):
            if line.startswith('#'):
                # Save previous chunk
                if current_chunk:
                    chunks.append(CodeChunk(
                        chunk_id=f"{file.path}:heading:{current_heading}",
                        file_path=file.path,
                        language=file.language,
                        chunk_type="heading",
                        start_line=start_line,
                        end_line=i - 1,
                        content='\n'.join(current_chunk),
                        function_name=current_heading,
                        file_hash=file_hash
                    ))
                
                # Start new chunk
                current_heading = line.lstrip('#').strip()
                current_chunk = [line]
                start_line = i
            else:
                current_chunk.append(line)
        
        # Add final chunk
        if current_chunk:
            chunks.append(CodeChunk(
                chunk_id=f"{file.path}:heading:{current_heading}",
                file_path=file.path,
                language=file.language,
                chunk_type="heading",
                start_line=start_line,
                end_line=len(lines),
                content='\n'.join(current_chunk),
                function_name=current_heading,
                file_hash=file_hash
            ))
        
        # Always return at least generic chunks if no chunks were created
        return chunks if chunks else self._chunk_generic(file) if chunks else self._chunk_generic(file)
    
    def _chunk_generic(self, file: RepositoryFile) -> List[CodeChunk]:
        """Fallback generic chunking using RecursiveCharacterTextSplitter."""
        chunks = []
        file_hash = generate_file_hash(file.content)
        text_chunks = self.fallback_splitter.split_text(file.content)
        
        for idx, chunk in enumerate(text_chunks):
            chunks.append(CodeChunk(
                chunk_id=f"{file.path}:generic:{idx}",
                file_path=file.path,
                language=file.language,
                chunk_type="generic",
                start_line=0,
                end_line=0,
                content=chunk,
                file_hash=file_hash
            ))
        
        return chunks


def chunk_repository(files: List[RepositoryFile]) -> List[CodeChunk]:
    """Chunk multiple files using code-aware chunking."""
    chunker = CodeAwareChunker()
    all_chunks = []
    
    for file in files:
        all_chunks.extend(chunker.chunk_file(file))
    
    return all_chunks
