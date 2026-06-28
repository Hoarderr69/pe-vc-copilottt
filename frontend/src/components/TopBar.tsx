import { useEffect, useRef, useState } from "react";
import type { ActionItem } from "../lib/api";

interface Props {
  pendingAlerts: number;
  topAlerts: ActionItem[];
  onGoToAlerts: () => void;
  darkMode: boolean;
  onToggleDark: () => void;
}

export function TopBar({ pendingAlerts, topAlerts, onGoToAlerts, darkMode, onToggleDark }: Props) {
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const alertsRef = useRef<HTMLDivElement>(null);
  const settingsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (alertsRef.current && !alertsRef.current.contains(e.target as Node)) setAlertsOpen(false);
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) setSettingsOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <header className="topbar">
      {/* Search */}
      <div className="topbar-search">
        <span className="material-symbols-outlined topbar-search-icon">search</span>
        <input className="topbar-search-input" placeholder="Search portfolio…" readOnly />
        <span className="topbar-search-hint">⌘K</span>
      </div>

      <div className="topbar-actions">
        {/* Bell */}
        <div className="topbar-icon-wrap" ref={alertsRef}>
          <button
            className="topbar-icon-btn"
            onClick={() => { setAlertsOpen(v => !v); setSettingsOpen(false); }}
            aria-label="Alerts"
          >
            <span className="material-symbols-outlined">notifications</span>
            {pendingAlerts > 0 && <span className="topbar-badge">{pendingAlerts}</span>}
          </button>

          {alertsOpen && (
            <div className="topbar-tray">
              <div className="topbar-tray-header">
                <span>Active Alerts</span>
                {pendingAlerts > 0 && <span className="topbar-tray-count">{pendingAlerts} pending review</span>}
              </div>
              {topAlerts.length === 0 ? (
                <div className="topbar-tray-empty">
                  <span className="material-symbols-outlined" style={{ fontSize: 28, opacity: 0.4 }}>check_circle</span>
                  <span>All clear — no active alerts</span>
                </div>
              ) : (
                <div className="topbar-tray-list">
                  {topAlerts.slice(0, 4).map((a, i) => (
                    <div key={i} className={`topbar-tray-item ${a.priority === "P1" ? "p1" : "p2"}`}>
                      <div className="topbar-tray-item-header">
                        <span className={`topbar-tray-pill ${a.priority === "P1" ? "red" : "amber"}`}>{a.priority}</span>
                        <span className="topbar-tray-company">{a.company_name}</span>
                      </div>
                      <p className="topbar-tray-headline">{a.headline}</p>
                    </div>
                  ))}
                </div>
              )}
              <button className="topbar-tray-footer" onClick={() => { setAlertsOpen(false); onGoToAlerts(); }}>
                View all in Alert Center
                <span className="material-symbols-outlined" style={{ fontSize: 14 }}>arrow_forward</span>
              </button>
            </div>
          )}
        </div>

        {/* Settings */}
        <div className="topbar-icon-wrap" ref={settingsRef}>
          <button
            className="topbar-icon-btn"
            onClick={() => { setSettingsOpen(v => !v); setAlertsOpen(false); }}
            aria-label="Settings"
          >
            <span className="material-symbols-outlined">settings</span>
          </button>

          {settingsOpen && (
            <div className="topbar-tray" style={{ minWidth: 220 }}>
              <div className="topbar-tray-header">Preferences</div>
              <div className="topbar-settings-list">
                <div className="topbar-settings-row" onClick={onToggleDark}>
                  <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                    {darkMode ? "light_mode" : "dark_mode"}
                  </span>
                  <span>{darkMode ? "Switch to Light Mode" : "Switch to Dark Mode"}</span>
                  <div className={`topbar-toggle ${darkMode ? "on" : ""}`}>
                    <div className="topbar-toggle-thumb" />
                  </div>
                </div>
                <div className="topbar-settings-divider" />
                <div className="topbar-settings-row muted" style={{ cursor: "default" }}>
                  <span className="material-symbols-outlined" style={{ fontSize: 16 }}>tune</span>
                  <span>Portfolio Preferences</span>
                  <span className="topbar-soon">Soon</span>
                </div>
                <div className="topbar-settings-row muted" style={{ cursor: "default" }}>
                  <span className="material-symbols-outlined" style={{ fontSize: 16 }}>notifications_active</span>
                  <span>Alert Thresholds</span>
                  <span className="topbar-soon">Soon</span>
                </div>
                <div className="topbar-settings-divider" />
                <div className="topbar-settings-row danger">
                  <span className="material-symbols-outlined" style={{ fontSize: 16 }}>logout</span>
                  <span>Sign Out</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Avatar */}
        <div className="topbar-avatar" title="Managing Partner">
          MP
        </div>
      </div>
    </header>
  );
}
