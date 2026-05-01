"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bot, BarChart2, FileText, Activity } from "lucide-react";

const NAV_ITEMS = [
  { href: "/",        label: "Chat",    icon: Bot },
  { href: "/traces",  label: "Traces",  icon: BarChart2 },
  { href: "/docs",    label: "Docs",    icon: FileText },
  { href: "/health",  label: "Health",  icon: Activity },
];

export function NavBar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 border-b bg-background/80 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        <div className="flex items-center gap-2 font-semibold text-sm">
          <Bot className="w-5 h-5 text-primary" />
          Multi-Agent System
        </div>
        <nav className="flex items-center gap-1">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
