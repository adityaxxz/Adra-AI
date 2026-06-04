
def planner_prompt(user_prompt: str, retrieved_context: str) -> str:
    PLANNER_PROMPT = f"""
        You are PLANNER agent, convert the USER prompt into a complete engineering project plan.

        user request : {user_prompt}
        
        Use the repository context when planning.
        Prefer modifying existing files over creating duplicate functionality.
        
        RELEVANT CODEBASE CONTEXT: {retrieved_context}
        """
    return PLANNER_PROMPT


def architect_prompt(plan: str) -> str:
    ARCHITECT_PROMPT = f"""
        You are the ARCHITECT agent. Given this project plan, break it down into explicit engineering tasks.

        Return a TaskPlan: a list of steps, each with filepath and task_description.

        RULES:
        - Create EXACTLY ONE step per file in the plan (no splitting a file across multiple steps).
        - Keep the total number of steps equal to the number of files in the plan.
        - Order steps by dependency: foundational/shared layers first, files that depend on them later.
        - In each task_description:
            * Specify exactly what to implement in that single file.
            * Name the key symbols (functions, classes, constants, types, config keys, public APIs).
            * State what this file exposes (exports, endpoints, schemas, interfaces) that other files will use.
            * State what this file must consume from other files (imports, calls, env vars, shared types).
        - Be concise but complete; avoid repeating the full project plan in every step.

        Project Plan: {plan}
    """
    return ARCHITECT_PROMPT


def coder_prompt( filepath: str, task_description: str, existing_content: str, project_context: str, plan_summary: str, repository_context: str = "", ) -> str:
    empty_note = "File is empty or new — implement from scratch." if not existing_content.strip() else ""
    repo_section = f"""
        
        REPOSITORY CONTEXT (relevant code from existing codebase):
        {repository_context}
        
        Use this repository context to understand existing patterns, APIs, and conventions.
        """ if repository_context.strip() else ""
    
    return f"""
        You are the CODER agent. Implement ONE file in a single response.

        Project: {plan_summary}
        File: {filepath}
        Task: {task_description}
        {empty_note}
        {repo_section}

        OTHER PROJECT FILES (already written — your code MUST integrate with these exactly):
        {project_context}

        Existing content of THIS file (if any):
        {existing_content}

        INTEGRATION RULES (critical):
        - Use only symbols, APIs, paths, and contracts defined in OTHER PROJECT FILES above or in REPOSITORY CONTEXT.
          Do NOT invent imports, module names, env keys, or endpoints that are not established elsewhere.
        - This file MUST expose every symbol or interface that dependent files are expected to use.
        - Import paths, module names, and references MUST match actual filenames and exports in the project.
        - Return runnable, production-ready code — no placeholders, no TODOs.

        Return the COMPLETE final file content only (not a diff, not markdown fences).
    """


def integrator_prompt(project_files: str, plan_summary: str) -> str:
    return f"""
        You are the INTEGRATOR agent. Review this generated project and fix cross-file bugs.

        Project: {plan_summary}

        ALL PROJECT FILES:
        {project_files}

        Check for:
        - References to symbols, modules, or APIs that do not exist in any other file
        - Missing exports or public interfaces that dependent files expect to call or import
        - Mismatched names between files (imports vs exports, config keys, shared constants)
        - Wrong file paths, module paths, or resource references
        - Logic bugs that prevent core features from working end-to-end

        Return updates ONLY for files that need fixes. Each update must be the FULL corrected file.
        If everything integrates correctly, return an empty updates list.
    """


def explainer_prompt(user_question: str, repository_context: str) -> str:
    return f"""
        You are the EXPLAINER agent. Answer the user's question about the codebase using the retrieved repository context.

        USER QUESTION: {user_question}

        REPOSITORY CONTEXT:
        {repository_context}

        INSTRUCTIONS:
        - Provide a clear, accurate answer based on the code context provided
        - Explain how the feature/implementation works
        - Reference specific files and code snippets when relevant
        - If the context doesn't contain enough information to answer, state what additional context would be needed
        - Be concise but thorough in your explanation

        Answer the user's question directly and informatively.
    """
