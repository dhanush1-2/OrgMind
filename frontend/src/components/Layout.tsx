import { Link, useLocation } from "react-router-dom";
import { Brain, Clock, Share2, AlertTriangle, Settings } from "lucide-react";

const NAV = [
  { to: "/", label: "Ask", icon: Brain },
  { to: "/timeline", label: "Timeline", icon: Clock },
  { to: "/graph", label: "Graph", icon: Share2 },
  { to: "/staleness", label: "Staleness", icon: AlertTriangle },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 border-r border-gray-800 flex flex-col">
        <div className="px-6 py-5 border-b border-gray-800">
          <span className="text-lg font-semibold text-indigo-400">OrgMind</span>
          <p className="text-xs text-gray-500 mt-0.5">AI Org Memory</p>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                pathname === to
                  ? "bg-indigo-600 text-white"
                  : "text-gray-400 hover:text-gray-100 hover:bg-gray-800"
              }`}
            >
              <Icon size={16} />
              {label}
            </Link>
          ))}
        </nav>
        <div className="px-6 py-4 border-t border-gray-800 text-xs text-gray-600">
          v0.1.0
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
