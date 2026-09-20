import { useEffect, useRef, useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { ArrowRight, CheckCircle2, CircleAlert, LogOut, ShieldCheck } from "lucide-react";
import AppShell from "@/components/AppShell";
import IntelligencePage from "@/pages/IntelligencePage";
import PlayerSearchPage from "@/pages/PlayerSearchPage";
import PlayerProfilePage from "@/pages/PlayerProfilePage";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Login = () => {
  const [error, setError] = useState("");
  const startGoogleSignIn = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };
  return (
    <main className="auth-page" data-testid="login-page">
      <section className="auth-panel" data-testid="login-panel">
        <div className="brand-mark" data-testid="brand-mark">FI</div>
        <p className="eyebrow" data-testid="login-eyebrow">FOOTBALL INTELLIGENCE OS</p>
        <h1 data-testid="login-heading">Your recruitment room, ready.</h1>
        <p className="auth-copy" data-testid="login-description">Sign in to continue to player intelligence, market signals, and decision-ready analysis.</p>
        <button className="google-button" data-testid="google-sign-in-button" onClick={startGoogleSignIn} type="button">
          <span className="google-g" aria-hidden="true">G</span> Continue with Google <ArrowRight size={17} aria-hidden="true" />
        </button>
        {error && <p className="error-message" data-testid="login-error"><CircleAlert size={16} /> {error}</p>}
        <p className="security-note" data-testid="login-security-note"><ShieldCheck size={15} /> Secure managed sign-in</p>
      </section>
      <aside className="auth-aside" data-testid="login-aside">
        <p className="aside-kicker" data-testid="aside-kicker">MATCH INTELLIGENCE / 01</p>
        <h2 data-testid="aside-heading">Turn evidence into the next move.</h2>
        <div className="signal-list" data-testid="login-feature-list">
          {['Player intelligence', 'Tactical fit', 'Market context'].map((item) => <div key={item} data-testid={`login-feature-${item.toLowerCase().replaceAll(' ', '-')}`}><CheckCircle2 size={16} /> {item}</div>)}
        </div>
      </aside>
    </main>
  );
};

const AuthCallback = () => {
  const navigate = useNavigate();
  const processed = useRef(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const sessionId = new URLSearchParams(window.location.hash.slice(1)).get("session_id");
    axios.post(`${API}/auth/session`, { session_id: sessionId }, { withCredentials: true })
      .then(({ data }) => navigate("/dashboard", { replace: true, state: { user: data.user } }))
      .catch(() => setError("We couldn't complete sign-in. Please return to login and try again."));
  }, [navigate]);
  return <main className="auth-page" data-testid="auth-callback-page"><section className="auth-panel callback-panel" data-testid="auth-callback-panel"><div className="brand-mark" data-testid="callback-brand-mark">FI</div><p className="eyebrow" data-testid="callback-eyebrow">SECURE SESSION</p><h1 data-testid="callback-heading">Opening your workspace…</h1><p className="auth-copy" data-testid="callback-status">{error || "Verifying your managed Google sign-in."}</p>{error && <button className="text-button" data-testid="callback-login-button" onClick={() => navigate("/login")}>Return to login</button>}</section></main>;
};

const ProtectedRoute = ({ children }) => {
  const location = useLocation();
  const [status, setStatus] = useState(null);
  const [user, setUser] = useState(location.state?.user || null);
  useEffect(() => {
    axios.get(`${API}/auth/me`, { withCredentials: true })
      .then(({ data }) => { setUser(data); setStatus(true); })
      .catch(() => setStatus(false));
  }, []);
  if (status === null) return <main className="loading-page" data-testid="auth-loading-state">Checking your session…</main>;
  if (!status) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children({ user });
};

const Dashboard = ({ user }) => {
  const navigate = useNavigate();
  const logout = async () => { await axios.post(`${API}/auth/logout`, {}, { withCredentials: true }); navigate("/login", { replace: true }); };
  return <AppShell><div data-testid="dashboard-page"><header className="workspace-header"><div><p className="eyebrow" data-testid="dashboard-eyebrow">FOOTBALL INTELLIGENCE OS / OVERVIEW</p><h1 data-testid="dashboard-heading">Good morning, {user.name.split(" ")[0]}.</h1><p className="workspace-subtitle" data-testid="dashboard-subtitle">Your decision room is connected and ready.</p></div><button className="logout-button" data-testid="logout-button" onClick={logout}><LogOut size={16} /> Sign out</button></header><section className="status-strip" data-testid="session-status"><span className="live-dot" /> <strong data-testid="session-status-label">SESSION ACTIVE</strong><span data-testid="session-user-email">{user.email}</span></section><section className="dashboard-grid" data-testid="dashboard-feature-grid">{['Player intelligence', 'Market signals', 'Match intelligence'].map((title, index) => <article className="intelligence-card" key={title} data-testid={`dashboard-card-${index + 1}`}><span className="card-number">0{index + 1}</span><h2 data-testid={`dashboard-card-title-${index + 1}`}>{title}</h2><p data-testid={`dashboard-card-status-${index + 1}`}>Connect a data source to begin.</p><span className="card-state" data-testid={`dashboard-card-state-${index + 1}`}>BACKEND DEPENDENCY</span></article>)}</section></div></AppShell>;
};

const WorkspaceRoute = ({ path }) => <AppShell><IntelligencePage path={path} /></AppShell>;

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return <Routes>
    <Route path="/login" element={<Login />} />
    <Route path="/dashboard" element={<ProtectedRoute>{({ user }) => <Dashboard user={user} />}</ProtectedRoute>} />
    <Route path="/players" element={<ProtectedRoute>{() => <AppShell><PlayerSearchPage /></AppShell>}</ProtectedRoute>} />
    <Route path="/players/:playerId" element={<ProtectedRoute>{() => <AppShell><PlayerProfilePage /></AppShell>}</ProtectedRoute>} />
    {Object.keys({ "/players/similarity": 1, "/market": 1, "/market/risk": 1, "/tactical/fit": 1, "/matches": 1, "/research": 1, "/copilot": 1 }).map((path) => <Route key={path} path={path} element={<ProtectedRoute>{() => <WorkspaceRoute path={path} />}</ProtectedRoute>} />)}
    <Route path="/" element={<Navigate to="/dashboard" replace />} />
    <Route path="*" element={<Navigate to="/dashboard" replace />} />
  </Routes>;
}

function App() {
  return <div className="App"><BrowserRouter><AppRouter /></BrowserRouter></div>;
}

export default App;
