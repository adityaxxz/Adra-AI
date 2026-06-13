import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col bg-[#09090b] text-[#fafafa]">
      {/* Navigation */}
      <nav className="glass-effect border-b border-zinc-800/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-3">
              <div className="w-9 h-9 flex items-center justify-center">
                <img src="/logo.png" alt="Adra-AI Logo" className="w-9 h-9 rounded-xl object-contain" />
              </div>
              <Link href="/" className="text-xl font-bold text-white tracking-tight">
                Adra-AI
              </Link>
            </div>
            <div className="flex items-center space-x-3">
              <Link
                href="/auth/signin"
                className="px-5 py-2.5 text-sm font-medium bg-zinc-800/50 hover:bg-zinc-700/50 text-white rounded-lg border border-zinc-700/50 transition-all duration-200 glass-effect hover:border-zinc-600"
              >
                Sign In
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <div className="flex-1 flex items-center justify-center px-4 sm:px-6 lg:px-8 relative overflow-hidden">
        {/* Background gradient effect */}
        <div className="absolute inset-0 bg-gradient-to-b from-violet-600/5 via-transparent to-transparent"></div>
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-violet-600/10 rounded-full blur-[120px]"></div>
        
        <div className="max-w-5xl text-center relative z-10">
          <div className="inline-flex items-center px-4 py-2 rounded-full bg-violet-600/10 border border-violet-500/20 text-violet-400 text-sm font-medium mb-8 backdrop-blur-sm">
            <span className="w-2 h-2 bg-violet-500 rounded-full mr-2 animate-pulse"></span>
            AI-Powered Development Platform
          </div>
          
          <h1 className="text-5xl sm:text-7xl font-bold text-white mb-6 tracking-tight leading-tight">
            Transform Ideas Into
            <br />
            <span className="bg-gradient-to-r from-violet-600 via-indigo-500 to-blue-500 bg-clip-text text-transparent">
              Code
            </span>
          </h1>
          <p className="text-xl text-zinc-400 mb-10 max-w-2xl mx-auto leading-relaxed">
            Generate full-stack applications, edit existing repositories, and get intelligent code assistance — all powered by advanced AI agents.
          </p>
          
          {/* Feature Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-12 mb-12">
            <div className="card card-hover p-6">
              <div className="w-12 h-12 bg-violet-600/10 rounded-xl flex items-center justify-center mb-4 border border-violet-500/20">
                <svg className="w-6 h-6 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Project Generation
              </h3>
              <p className="text-zinc-400 text-sm leading-relaxed">
                Generate complete applications from natural language descriptions
              </p>
            </div>

            <div className="card card-hover p-6">
              <div className="w-12 h-12 bg-indigo-600/10 rounded-xl flex items-center justify-center mb-4 border border-indigo-500/20">
                <svg className="w-6 h-6 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Repository Editing
              </h3>
              <p className="text-zinc-400 text-sm leading-relaxed">
                Edit and improve existing codebases with AI-powered assistance
              </p>
            </div>

            <div className="card card-hover p-6">
              <div className="w-12 h-12 bg-blue-600/10 rounded-xl flex items-center justify-center mb-4 border border-blue-500/20">
                <svg className="w-6 h-6 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Code Understanding
              </h3>
              <p className="text-zinc-400 text-sm leading-relaxed">
                Ask questions about your codebase and get intelligent answers
              </p>
            </div>
          </div>

          {/* CTA Buttons */}
          <div className="flex items-center justify-center">
            <Link
              href="/auth/signin"
              className="inline-flex items-center px-8 py-4 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-medium rounded-xl transition-all duration-200 shadow-lg shadow-violet-500/25 hover:shadow-xl hover:shadow-violet-500/30"
            >
              Get Started Free
              <svg className="w-5 h-5 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </Link>
          </div>
          
          <p className="mt-8 text-sm text-zinc-500">
            No credit card required • Start building in seconds
          </p>
        </div>
      </div>
    </div>
  );
}
