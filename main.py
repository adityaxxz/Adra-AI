import argparse
import sys
import traceback

from agent.graph import agent
from agent.llm_client import get_stats


def main():
    parser = argparse.ArgumentParser(description="Run engineering project planner")
    parser.add_argument("--recursion-limit", "-r", type=int, default=100,
                        help="Recursion limit for processing (default: 100)")

    args = parser.parse_args()

    try:
        user_prompt = input("Enter your project prompt: ")
        
        result = agent.invoke(
            {"user_prompt": user_prompt},
            {"recursion_limit": args.recursion_limit}
        )

        stats = get_stats()
        fixes = result.get("integration_fixes", 0)
        print(f"LLM API calls: {stats['api_calls']} (throttle: {stats['min_interval_sec']}s between calls)")

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