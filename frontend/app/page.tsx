import Link from "next/link";

export default function Home() {
  return (
    <div
      className="min-h-screen flex flex-col relative overflow-hidden"
      style={{ background: 'var(--bg-base)', color: 'var(--text-primary)' }}
    >
      {/* Animated background orbs */}
      <div
        className="orb orb-violet animate-orb-float"
        style={{ width: 700, height: 700, top: -200, left: '50%', transform: 'translateX(-50%)' }}
      />
      <div
        className="orb orb-indigo animate-orb-float delay-400"
        style={{ width: 400, height: 400, bottom: 0, right: -100 }}
      />

      {/* Navigation */}
      <nav
        className="relative z-10 flex items-center justify-between px-8 py-5 border-b"
        style={{ borderColor: 'var(--border)', background: 'rgba(10,10,15,0.8)', backdropFilter: 'blur(16px)' }}
      >
        <div className="flex items-center gap-3">
          <img src="/logo.png" alt="Adra-AI" className="w-8 h-8 rounded-lg object-contain" />
          <span className="text-base font-bold text-white tracking-tight">Adra-AI</span>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/auth/signin"
            className="btn-secondary text-sm"
            id="sign-in-nav"
          >
            Sign In
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 pt-20 pb-24 text-center">
        {/* Badge */}
        <div
          className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-medium mb-8 animate-fade-in"
          style={{
            background: 'rgba(139,92,246,0.1)',
            border: '1px solid rgba(139,92,246,0.25)',
            color: '#a78bfa',
          }}
        >
          <span className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
          AI-Powered Codebase Intelligence
        </div>

        {/* Headline */}
        <h1
          className="text-6xl sm:text-7xl lg:text-8xl font-extrabold text-white tracking-tighter leading-[1.05] mb-6 animate-fade-in-up"
          style={{ letterSpacing: '-0.04em' }}
        >
          Build smarter
          <br />
          <span className="gradient-text">with AI agents</span>
        </h1>

        {/* Subheadline */}
        <p
          className="text-lg sm:text-xl max-w-2xl mx-auto mb-10 leading-relaxed animate-fade-in-up delay-100"
          style={{ color: 'var(--text-secondary)' }}
        >
          Generate full-stack applications, edit existing repositories, and get intelligent code
          assistance — all powered by advanced AI agents that understand your codebase.
        </p>

        {/* CTA */}
        <div className="flex flex-col sm:flex-row items-center gap-4 mb-20 animate-fade-in-up delay-200">
          <Link
            href="/auth/signin"
            className="btn-primary px-8 py-3.5 text-base glow-btn"
            id="hero-cta"
          >
            Start Building Free
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </Link>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            No credit card required
          </p>
        </div>

        {/* Feature Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 max-w-5xl w-full animate-fade-in-up delay-300">
          {[
            {
              icon: (
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              ),
              color: '#8b5cf6',
              colorBg: 'rgba(139,92,246,0.1)',
              colorBorder: 'rgba(139,92,246,0.2)',
              title: 'Project Generation',
              desc: 'Generate complete full-stack applications from a natural language description in seconds.',
            },
            {
              icon: (
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              ),
              color: '#6366f1',
              colorBg: 'rgba(99,102,241,0.1)',
              colorBorder: 'rgba(99,102,241,0.2)',
              title: 'Repository Editing',
              desc: 'Upload your existing codebase and let AI make intelligent edits across multiple files.',
            },
            {
              icon: (
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              ),
              color: '#3b82f6',
              colorBg: 'rgba(59,130,246,0.1)',
              colorBorder: 'rgba(59,130,246,0.2)',
              title: 'Code Understanding',
              desc: 'Ask questions about any codebase and receive accurate, context-aware answers instantly.',
            },
          ].map((feature, i) => (
            <div
              key={i}
              className="card p-6 text-left card-hover"
              style={{ background: 'rgba(17,17,24,0.7)', backdropFilter: 'blur(12px)' }}
            >
              <div
                className="w-11 h-11 rounded-xl flex items-center justify-center mb-4"
                style={{ background: feature.colorBg, border: `1px solid ${feature.colorBorder}`, color: feature.color }}
              >
                {feature.icon}
              </div>
              <h3 className="text-base font-semibold text-white mb-2">{feature.title}</h3>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {feature.desc}
              </p>
            </div>
          ))}
        </div>

        {/* Stats row */}
        {/* <div
          className="flex flex-wrap items-center justify-center gap-10 mt-16 animate-fade-in-up delay-400"
          style={{ color: 'var(--text-muted)' }}
        >
          {[
            { value: 'Multi-file', label: 'Edits in one shot' },
            { value: 'Full-stack', label: 'App generation' },
            { value: 'Real-time', label: 'AI streaming' },
          ].map((stat) => (
            <div key={stat.label} className="text-center">
              <p className="text-2xl font-bold text-white mb-0.5">{stat.value}</p>
              <p className="text-xs">{stat.label}</p>
            </div>
          ))}
        </div> */}
      </main>

      {/* Footer */}
      <footer
        className="relative z-10 text-center py-6 text-xs border-t"
        style={{ color: 'var(--text-muted)', borderColor: 'var(--border)' }}
      >
        © {new Date().getFullYear()} Adra-AI
      </footer>
    </div>
  );
}
