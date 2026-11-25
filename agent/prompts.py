
def planner_prompt(user_prompt: str) -> str:
    """Plan a project built from scratch. Editing an existing repository goes
    through `edit_planner_prompt` instead."""
    PLANNER_PROMPT = f"""
        You are PLANNER agent, convert the USER prompt into a complete engineering project plan.

        user request : {user_prompt}

        DEPENDENCY MANIFEST: if the project uses any third-party package, the plan's files MUST include the manifest
        that declares them: requirements.txt for Python, package.json for JavaScript/Node. A project that uses only
        the standard library (or only browser APIs) needs none.
        """
    return PLANNER_PROMPT


def edit_planner_prompt(user_prompt: str, retrieved_context: str, repo_files: str) -> str:
    return f"""
        You are the EDIT PLANNER. Plan the smallest set of file changes that satisfies
        the user's request in an EXISTING repository.

        USER REQUEST: {user_prompt}

        FILES THAT CURRENTLY EXIST IN THIS REPOSITORY:
        {repo_files}

        RELEVANT CODE RETRIEVED FROM THIS REPOSITORY:
        {retrieved_context}

        RULES:
        - Prefer modifying existing files over creating new ones. Add a file only when
          the request genuinely cannot be satisfied by editing what is already there.
        - Every filepath must appear in the file list above, unless the user explicitly
          asked for a new file to be created. If the request names a file that is not
          listed but is clearly a misspelling of exactly one listed file (e.g. `style.cc`
          for `style.css`), edit the listed file. Never invent or guess a path.
        - Exactly one entry per file — never split one file across multiple entries.
        - Order entries by dependency: shared/foundational files before their consumers.
        - In each change_description, state precisely what to add, modify or remove and
          name the concrete symbols involved (functions, classes, routes, config keys).
        - If the request does not ask for any change to the repository (for example it is
          a question), return an EMPTY edits list and say so in the summary.
        - You can only modify or create files. You cannot delete, rename or move a file.
          Plan the edits you can make, and state in the summary what you could not do.
        - Do NOT restructure the project, rename existing modules, reformat code, or
          touch anything unrelated to the request.
        - Keep the plan minimal. Do not invent features the user did not ask for.
        - The retrieved code above is a partial excerpt, not the whole repository. Do not
          assume something is missing just because it isn't shown.

        Return a one-line summary of the overall change plus the ordered list of file edits.
    """


def architect_prompt(plan: str) -> str:
    ARCHITECT_PROMPT = f"""
        You are the ARCHITECT agent. Given this project plan, break it down into explicit engineering tasks.

        Return a TaskPlan: a list of steps, each with filepath and task_description.

        RULES:
        - Create EXACTLY ONE step per file in the plan (no splitting a file across multiple steps).
        - Keep the total number of steps equal to the number of files in the plan.
        - Order steps by dependency: foundational/shared layers first, files that depend on them later.
        - EXCEPTION: the dependency manifest (requirements.txt, package.json) is ALWAYS the LAST step, so that the
          coder writing it can see every other file. Its task_description must say: declare every third-party package
          imported anywhere in the project, and nothing that is only part of the standard library.
        - If the project defines database models with an ORM (e.g. SQLAlchemy, SQLModel), the task for the application's
          entry point (e.g. main.py) must include creating the tables at startup, after the models are imported
          (e.g. Base.metadata.create_all(bind=engine)). Without it the first request fails with "no such table".
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
    empty_note = (
        "File is empty or new — implement from scratch."
        if not existing_content.strip()
        else "This file already exists. Change ONLY what the Task requires and keep every other line "
             "exactly as it is (same formatting, comments and ordering). Never drop existing code."
    )
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
        - If THIS file is a dependency manifest (requirements.txt, package.json), derive it from OTHER PROJECT FILES:
          list EVERY third-party package they import (including the database layer, validation and server libraries,
          e.g. SQLAlchemy, pydantic, uvicorn) and nothing that is only in the standard library.
        - Return runnable, production-ready code — no placeholders, no TODOs.

        Return the COMPLETE final file content only (not a diff, not markdown fences).
    """


# Only for a project generated from scratch: an existing repository may create its tables through migrations.
_NEW_PROJECT_CHECKS = """
        - Database tables that are never created: if ORM models are defined (e.g. SQLAlchemy, SQLModel) but nothing
          calls metadata.create_all(...) when the app starts, add it to the entry point after the models are imported."""


def integrator_prompt(project_files: str, plan_summary: str, reference_context: str = "", new_project: bool = False) -> str:
    reference_section = f"""

        REFERENCE CONTEXT (pre-existing code, read-only — you may NOT return updates for these):
        {reference_context}
        """ if reference_context.strip() else ""

    return f"""
        You are the INTEGRATOR agent. Review the files changed by this task and fix cross-file bugs.

        Project: {plan_summary}

        FILES TO REVIEW (these are the only files you may correct):
        {project_files}
        {reference_section}

        Check for:
        - References to symbols, modules, or APIs that do not exist in any other file
        - Missing exports or public interfaces that dependent files expect to call or import
        - Mismatched names between files (imports vs exports, config keys, shared constants)
        - Wrong file paths, module paths, or resource references
        - Logic bugs that prevent core features from working end-to-end{_NEW_PROJECT_CHECKS if new_project else ""}

        SCOPE RULES (critical):
        - Return updates ONLY for files listed under FILES TO REVIEW. Updates for any other
          path will be discarded.
        - Files not shown above are outside the scope of this change. Do NOT assume a
          referenced symbol, module, or import is missing just because its definition is
          not included here — only flag a reference you can positively confirm is broken.

        Each update must be the FULL corrected file.
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
        - If the question asks for a particular length or format (for example "in short", "briefly", "in one line", "in detail"), follow that exactly: a short answer is two or three sentences with no headings, tables or bullet lists
        - Otherwise be concise but thorough in your explanation

        Answer the user's question directly and informatively.
    """
