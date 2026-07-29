"use client";

import type { ReactNode } from "react";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import StatusBar from "./StatusBar";

interface DashboardLayoutProps {
  children: ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  return (
    <div className="flex h-screen flex-col">
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <div className="flex flex-1 flex-col lg:pl-16">
          <Topbar />
          <main className="flex-1 overflow-y-auto bg-[var(--color-bg-base)] p-4 sm:p-6">
            {children}
          </main>
        </div>
      </div>
      <StatusBar />
    </div>
  );
}
