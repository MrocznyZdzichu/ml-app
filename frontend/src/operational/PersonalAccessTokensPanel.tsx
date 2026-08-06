import { Copy, KeyRound, RotateCcw, ShieldCheck, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { PersonalAccessToken } from "../api/client";

type NoticeSetter = (message: string) => void;
type Lifetime = "6h" | "24h" | "7d" | "30d" | "custom" | "never";

const lifetimeMilliseconds: Record<Exclude<Lifetime, "custom" | "never">, number> = {
  "6h": 6 * 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  "30d": 30 * 24 * 60 * 60 * 1000
};

function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Never";
}

function expiryFrom(lifetime: Lifetime, customExpiry: string): string | null {
  if (lifetime === "never") return null;
  if (lifetime === "custom") {
    const date = new Date(customExpiry);
    if (!customExpiry || Number.isNaN(date.valueOf()) || date <= new Date()) {
      throw new Error("Choose a future expiry date and time");
    }
    return date.toISOString();
  }
  return new Date(Date.now() + lifetimeMilliseconds[lifetime]).toISOString();
}

export function PersonalAccessTokensPanel({ setNotice }: { setNotice: NoticeSetter }) {
  const [tokens, setTokens] = useState<PersonalAccessToken[]>([]);
  const [name, setName] = useState("notebook");
  const [lifetime, setLifetime] = useState<Lifetime>("6h");
  const [customExpiry, setCustomExpiry] = useState("");
  const [createdToken, setCreatedToken] = useState("");
  const [createdExpiry, setCreatedExpiry] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      setTokens(await api.listPersonalAccessTokens());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load personal access tokens");
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function createToken() {
    setError("");
    const cleanName = name.trim();
    if (!cleanName) {
      setError("Give this token a recognizable name");
      return;
    }
    let expiresAt: string | null;
    try {
      expiresAt = expiryFrom(lifetime, customExpiry);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Invalid expiry");
      return;
    }
    setBusy(true);
    try {
      const created = await api.createPersonalAccessToken(cleanName, expiresAt);
      setCreatedToken(created.token);
      setCreatedExpiry(created.expires_at);
      setNotice("Personal access token created. Copy it now; it will not be shown again.");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create personal access token");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(token: PersonalAccessToken) {
    if (!window.confirm(`Revoke personal access token ${JSON.stringify(token.name)}? Existing clients using it will lose access immediately.`)) return;
    setBusy(true);
    setError("");
    try {
      await api.revokePersonalAccessToken(token.id);
      setTokens((current) => current.map((item) => item.id === token.id ? { ...item, revoked_at: new Date().toISOString() } : item));
      setNotice(`Personal access token ${token.name} revoked`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not revoke personal access token");
    } finally {
      setBusy(false);
    }
  }

  return <div className="personal-tokens-content" role="region" aria-label="Personal access tokens">
    <section className="panel">
      <div className="panel-header"><div><span className="builder-kicker">Account security</span><h2>Personal access tokens</h2><p>Authenticate scripts and notebooks as your account without entering your password. Each token has all of your current platform permissions; it is not limited to one Serving endpoint.</p></div><KeyRound size={18} /></div>
      <div className="personal-token-warning"><ShieldCheck size={18} /><span>Choose the shortest useful lifetime. A token is shown only once, is stored hashed by the platform, and can be revoked immediately.</span></div>
      {error && <div className="error-banner" role="alert">{error}</div>}
      <div className="personal-token-form">
        <label>Name<input value={name} maxLength={255} onChange={(event) => setName(event.target.value)} placeholder="e.g. customer-analysis-notebook" /></label>
        <label>Lifetime<select value={lifetime} onChange={(event) => setLifetime(event.target.value as Lifetime)}><option value="6h">6 hours</option><option value="24h">24 hours</option><option value="7d">7 days</option><option value="30d">30 days</option><option value="custom">Custom expiry</option><option value="never">No expiry (not recommended)</option></select></label>
        {lifetime === "custom" && <label>Expires at<input type="datetime-local" value={customExpiry} onChange={(event) => setCustomExpiry(event.target.value)} /></label>}
        <button className="primary-button" type="button" onClick={() => void createToken()} disabled={busy}><KeyRound size={15} /> Create token</button>
      </div>
      {createdToken && <div className="personal-token-once"><div><strong>Copy your token now</strong><span>It {createdExpiry ? `expires ${formatDate(createdExpiry)}` : "does not expire"} and will not be displayed again after you dismiss this message.</span></div><code>{createdToken}</code><div className="catalog-toolbar-actions"><button className="secondary-button" type="button" onClick={() => void navigator.clipboard.writeText(createdToken)}><Copy size={15} /> Copy token</button><button className="secondary-button" type="button" onClick={() => setCreatedToken("")}>Done</button></div></div>}
    </section>

    <section className="panel">
      <div className="panel-header"><div><h2>Active and historical tokens</h2><p>Revocation immediately rejects the token. A token’s plaintext value is never recoverable.</p></div><button className="secondary-button compact-button" type="button" onClick={() => void refresh()} disabled={busy}><RotateCcw size={14} /> Refresh</button></div>
      <div className="personal-token-list">
        {tokens.map((token) => <article key={token.id} className={token.revoked_at ? "revoked" : ""}><div><strong>{token.name}</strong><small>Created {formatDate(token.created_at)} · Last used {formatDate(token.last_used_at)}</small></div><span><small>{token.revoked_at ? `Revoked ${formatDate(token.revoked_at)}` : `Expires ${formatDate(token.expires_at)}`}</small>{!token.revoked_at && <button className="icon-button danger-button" type="button" aria-label={`Revoke ${token.name}`} title="Revoke token" onClick={() => void revoke(token)} disabled={busy}><Trash2 size={15} /></button>}</span></article>)}
        {!tokens.length && <div className="empty-state"><KeyRound size={22} /><strong>No personal access tokens</strong><span>Create a short-lived token for a notebook or script.</span></div>}
      </div>
    </section>
  </div>;
}
