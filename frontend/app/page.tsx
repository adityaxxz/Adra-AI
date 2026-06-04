import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Navigation */}
      <nav className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
                Adra-AI
              </h1>
            </div>
            <div className="flex items-center space-x-4">
              <Link
                href="/auth/google"
                className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-200 hover:text-slate-900 dark:hover:text-white"
              >
                Sign In with Google
              </Link>
              <Link
                href="/auth/github"
                className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-200 hover:text-slate-900 dark:hover:text-white"
              >
                Sign In with GitHub
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <div className="flex-1 flex items-center justify-center px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl text-center">
          <h2 className="text-4xl sm:text-5xl font-extrabold text-slate-900 dark:text-white mb-6">
            Transform Ideas Into Code with AI
          </h2>
          <p className="text-xl text-slate-600 dark:text-slate-300 mb-8">
            Generate full-stack applications, edit existing repositories, and get intelligent code assistance - all powered by advanced AI agents.
          </p>
          
          {/* Feature Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-12">
            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 border border-slate-200 dark:border-slate-700">
              <div className="text-3xl mb-4">🚀</div>
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
                Project Generation
              </h3>
              <p className="text-slate-600 dark:text-slate-300 text-sm">
                Generate complete applications from natural language descriptions
              </p>
            </div>

            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 border border-slate-200 dark:border-slate-700">
              <div className="text-3xl mb-4">🔧</div>
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
                Repository Editing
              </h3>
              <p className="text-slate-600 dark:text-slate-300 text-sm">
                Edit and improve existing codebases with AI-powered assistance
              </p>
            </div>

            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 border border-slate-200 dark:border-slate-700">
              <div className="text-3xl mb-4">📚</div>
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
                Code Understanding
              </h3>
              <p className="text-slate-600 dark:text-slate-300 text-sm">
                Ask questions about your codebase and get intelligent answers
              </p>
            </div>
          </div>

          {/* CTA Button */}
          <div className="mt-12">
            <Link
              href="/auth/google"
              className="inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700"
            >
              Get Started
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
