import { LogIn, UserPlus } from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { api } from "../api/client";

export function AuthScreen({
  apiStatus,
  isChecking,
  onAuthenticated
}: {
  apiStatus: string;
  isChecking: boolean;
  onAuthenticated: (token: string) => Promise<void>;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("demo@example.com");
  const [displayName, setDisplayName] = useState("Demo Analyst");
  const [password, setPassword] = useState("password123");
  const [message, setMessage] = useState(isChecking ? "Checking session" : "Sign in to continue");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isChecking && message === "Checking session") {
      setMessage("Sign in to continue");
    }
  }, [isChecking, message]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    setMessage(mode === "login" ? "Signing in" : "Creating account");
    try {
      const response = mode === "login"
        ? await api.login({ email, password })
        : await api.register({ email, password, display_name: displayName });
      await onAuthenticated(response.access_token);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Authentication failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-panel">
        <div className="brand auth-brand">
          <div className="brand-mark">ML</div>
          <div>
            <strong>ML App</strong>
            <span>Private analytics workspace</span>
          </div>
        </div>

        <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
          <button
            className={mode === "login" ? "active" : ""}
            onClick={() => setMode("login")}
            type="button"
          >
            <LogIn size={16} />
            Login
          </button>
          <button
            className={mode === "register" ? "active" : ""}
            onClick={() => setMode("register")}
            type="button"
          >
            <UserPlus size={16} />
            Register
          </button>
        </div>

        <form className="auth-form" onSubmit={submit}>
          <label>
            Email
            <input
              autoComplete="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          {mode === "register" && (
            <label>
              Display name
              <input
                autoComplete="name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </label>
          )}
          <label>
            Password
            <input
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={6}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          <button className="primary-button" disabled={isSubmitting || isChecking} type="submit">
            {mode === "login" ? <LogIn size={16} /> : <UserPlus size={16} />}
            {mode === "login" ? "Login" : "Create account"}
          </button>
        </form>

        <div className="auth-footer">
          <span>{message}</span>
          <span>API {apiStatus}</span>
        </div>
      </section>
    </main>
  );
}
