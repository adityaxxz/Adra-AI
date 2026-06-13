import argparse
import sys
import traceback
from pathlib import Path

from agent.graph import project_generation_agent, repository_editing_agent, question_answering_agent
from agent.llm_client import get_stats
from agent.repository.service import index_repository, clone_github_repo
from agent.repository.vector_store import set_active_collection
from agent.tools import set_project_root, init_project_root


def main():
    # Initialize default project root for project generation mode
    init_project_root()
    
    parser = argparse.ArgumentParser(description="Adra-AI: Project generator and repository-aware AI coding assistant")
    parser.add_argument("--recursion-limit", "-r", type=int, default=100,
                        help="Recursion limit for processing (default: 100)")
    parser.add_argument("--repo", type=str, default=None,
                        help="Path to local repository for repository-aware editing mode")
    parser.add_argument("--github", type=str, default=None,
                        help="GitHub repository URL for repository-aware editing mode")
    parser.add_argument("--collection", type=str, default=None,
                        help="ChromaDB collection name for repository (default: auto-generated from repo name)")
    parser.add_argument("--ask", action="store_true",
                        help="Ask question mode: answer questions about the codebase without making changes")

    args = parser.parse_args()

    # Determine workflow mode
    repo_path = None
    collection_name = None

    if args.github:
        # GitHub ingestion mode
        print(f"Cloning GitHub repository: {args.github}")
        try:
            repo_path = clone_github_repo(args.github)
            # Generate collection name from repo URL
            collection_name = args.collection or args.github.split('/')[-1].replace('.git', '')
            print(f"Indexing repository into collection: {collection_name}")
            index_repository(repo_path, collection_name=collection_name)
            print("Repository indexed successfully.")
        except Exception as e:
            print(f"Error cloning/indexing repository: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.repo:
        # Local repository mode
        repo_path = args.repo
        if not Path(repo_path).exists():
            print(f"Error: Repository path does not exist: {repo_path}", file=sys.stderr)
            sys.exit(1)
        collection_name = args.collection or Path(repo_path).name
        print(f"Indexing local repository into collection: {collection_name}")
        try:
            index_repository(repo_path, collection_name=collection_name)
            print("Repository indexed successfully.")
        except Exception as e:
            print(f"Error indexing repository: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Project generation mode (default)
        print("Mode: Project Generation (new project from scratch)")

    try:
        user_prompt = input("Enter your prompt: ")
        
        # Select appropriate agent based on mode
        if repo_path:
            if args.ask:
                print("Mode: Repository Question Answering")
                set_project_root(repo_path)
                set_active_collection(collection_name)
                agent = question_answering_agent
                initial_state = {
                    "user_prompt": user_prompt,
                    "repo_path": repo_path,
                    "collection_name": collection_name
                }
            else:
                print("Mode: Repository-Aware Editing")
                set_project_root(repo_path)
                set_active_collection(collection_name)
                agent = repository_editing_agent
                initial_state = {
                    "user_prompt": user_prompt,
                    "repo_path": repo_path,
                    "collection_name": collection_name
                }
        else:
            agent = project_generation_agent
            initial_state = {"user_prompt": user_prompt}
        
        result = agent.invoke(
            initial_state,
            {"recursion_limit": args.recursion_limit}
        )

        stats = get_stats()
        print(f"LLM API calls: {stats['api_calls']} (throttle: {stats['min_interval_sec']}s between calls)")

        if args.ask:
            # Display the answer for question-answering mode
            answer = result.get("answer", "No answer generated.")
            print(f"\nAnswer: {answer}")
        else:
            fixes = result.get("integration_fixes", 0)
            if fixes:
                print(f"Integration fixes applied: {fixes} file(s)")
            print("Final State:", result)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)

    except Exception as e:
        traceback.print_exc()
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()