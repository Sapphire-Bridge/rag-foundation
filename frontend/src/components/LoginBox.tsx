import React, { useMemo, useState } from "react";
import { validatePassword } from "../utils/passwordValidation";

export const LoginBox: React.FC<{ onToken: (t: string) => void }> = ({ onToken }) => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");
  const { isValid, checks } = useMemo(() => validatePassword(password), [password]);
  const showDevLogin = !import.meta.env.PROD && (import.meta.env.DEV || import.meta.env.VITE_ALLOW_DEV_LOGIN === "true");

  const login = async () => {
    setStatus("Logging in…");
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: {"Content-Type":"application/json", "X-Requested-With": "XMLHttpRequest"},
      body: JSON.stringify({ email, password })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setStatus(`Error: ${err?.detail || res.statusText}`);
      return;
    }
    const data = await res.json();
    sessionStorage.setItem("lastLoginEmail", email);
    onToken(data.access_token);
    setStatus("Logged in ✅");
  };

  const register = async () => {
    if (!isValid) {
      setStatus("Password must meet all requirements.");
      return;
    }
    setStatus("Registering…");
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: {"Content-Type":"application/json", "X-Requested-With": "XMLHttpRequest"},
      body: JSON.stringify({ email, password })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setStatus(`Error: ${err?.detail || res.statusText}`);
      return;
    }
    setStatus("Registered. You can log in now.");
  };

  const devLogin = async () => {
    setStatus("Dev token…");
    const res = await fetch("/api/auth/token", {
      method: "POST",
      headers: {"Content-Type":"application/json", "X-Requested-With": "XMLHttpRequest"},
      body: JSON.stringify({ email })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setStatus(`Error: ${err?.detail || res.statusText}`);
      return;
    }
    const data = await res.json();
    sessionStorage.setItem("lastLoginEmail", email);
    onToken(data.access_token);
    setStatus("Dev token acquired ✅");
  };

  return (
    <div className="space-y-2 pb-4 border-b border-border mb-4">
      <input
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="w-full px-3 py-2 bg-background border border-input rounded-md"
      />
      <input
        type="password"
        placeholder="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full px-3 py-2 bg-background border border-input rounded-md"
      />
      {password && (
        <div className="bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-lg px-4 py-3 space-y-2">
          <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">Password Requirements</p>
          <ul className="grid grid-cols-2 gap-x-4 gap-y-1.5">
            {checks.map((c) => (
              <li
                key={c.msg}
                className={`flex items-center gap-2 text-xs transition-colors ${
                  c.valid
                    ? "text-slate-900 dark:text-slate-100"
                    : "text-slate-400 dark:text-slate-500"
                }`}
              >
                <span className={`flex-shrink-0 w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold transition-colors ${
                  c.valid
                    ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 ring-1 ring-blue-200 dark:ring-blue-800"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-600"
                }`}>
                  {c.valid ? "✓" : "○"}
                </span>
                <span className="leading-tight font-medium">{c.msg}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="grid grid-cols-2 gap-2">
        <button onClick={login} className="px-3 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90">Login</button>
        <button
          onClick={register}
          disabled={!isValid}
          className="px-3 py-2 bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Register
        </button>
      </div>
      <div className="flex gap-2 items-center flex-wrap">
        {showDevLogin && (
          <button
            onClick={devLogin}
            title="Development-only login is hidden in production builds"
            className="px-3 py-1 text-sm bg-muted text-muted-foreground rounded-md hover:bg-muted/80"
          >
            Dev Token
          </button>
        )}
        {showDevLogin && <span className="text-[11px] font-medium text-muted-foreground">Development only</span>}
        <span className="text-xs text-muted-foreground">{status}</span>
      </div>
    </div>
  );
};
