import { useEffect, useRef, useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { ArrowRight, CheckCircle2, CircleAlert, ShieldCheck } from "lucide-react";
import AppShell from "@/components/AppShell";
import DashboardPage from "@/pages/DashboardPage";
import PlayerSearchPage from "@/pages/PlayerSearchPage";
import PlayerProfilePage from "@/pages/PlayerProfilePage";
import PlayerComparePage from "@/pages/PlayerComparePage";
import SimilarityPage from "@/pages/SimilarityPage";
import RolesPage from "@/pages/RolesPage";
import MarketPage from "@/pages/MarketPage";
import TacticalFitPage from "@/pages/TacticalFitPage";
import MatchesPage from "@/pages/MatchesPage";
import SquadPage from "@/pages/SquadPage";
import ResearchPage from "@/pages/ResearchPage";
import DataQualityPage from "@/pages/DataQualityPage";
import CopilotPage from "@/pages/CopilotPage";
import ShortlistsPage from "@/pages/ShortlistsPage";
import SharedShortlistPage from "@/pages/SharedShortlistPage";
import DecisionPage from "@/pages/DecisionPage";
import RecruitmentProjectsPage from "@/pages/RecruitmentProjectsPage";
import WatchlistsPage from "@/pages/WatchlistsPage";
import ScenariosPage from "@/pages/ScenariosPage";
import OperationsPage from "@/pages/OperationsPage";
import GlobalOperationsPage from "@/pages/GlobalOperationsPage";
import ContinuousIntelligencePage from "@/pages/ContinuousIntelligencePage";
import DecisionLabPage from "@/pages/DecisionLabPage";
import OutcomeIntelligencePage from "@/pages/OutcomeIntelligencePage";

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
        <h1 data-testid="login-heading">A recruitment room built on evidence.</h1>
        <p className="auth-copy" data-testid="login-description">Sign in to open a decision surface for player intelligence, role fit, market context, and match analysis — every number linked to its source.</p>
        <button className="google-button" data-testid="google-sign-in-button" onClick={startGoogleSignIn} type="button">
          <span className="google-g" aria-hidden="true">G</span> Continue with Google <ArrowRight size={16} aria-hidden="true" />
        </button>
        {error && <p className="error-message" data-testid="login-error"><CircleAlert size={16} /> {error}</p>}
        <p className="security-note" data-testid="login-security-note"><ShieldCheck size={14} /> Managed Google sign-in · session encrypted end-to-end</p>
      </section>
      <aside className="auth-aside" data-testid="login-aside">
        <p className="aside-kicker" data-testid="aside-kicker">MATCH INTELLIGENCE / 01</p>
        <h2 data-testid="aside-heading">Turn evidence into the next move.</h2>
        <div className="signal-list" data-testid="login-feature-list">
          {['Player intelligence & role discovery', 'Similarity & tactical fit', 'Market context with provenance'].map((item) => (
            <div key={item} data-testid={`login-feature-${item.toLowerCase().replaceAll(' ', '-').replaceAll('&', 'and')}`}>
              <CheckCircle2 size={15} /> {item}
            </div>
          ))}
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
  return (
    <main className="auth-page" data-testid="auth-callback-page">
      <section className="auth-panel callback-panel" data-testid="auth-callback-panel">
        <div className="brand-mark" data-testid="callback-brand-mark">FI</div>
        <p className="eyebrow" data-testid="callback-eyebrow">SECURE SESSION</p>
        <h1 data-testid="callback-heading">Opening your workspace…</h1>
        <p className="auth-copy" data-testid="callback-status">{error || "Verifying your managed Google sign-in."}</p>
        {error && <button className="text-button" data-testid="callback-login-button" onClick={() => navigate("/login")}>Return to login</button>}
      </section>
    </main>
  );
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

const withShell = (element) => <AppShell>{element}</AppShell>;

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/shared/shortlists/:token" element={<SharedShortlistPage />} />
      <Route path="/dashboard" element={<ProtectedRoute>{({ user }) => withShell(<DashboardPage user={user} />)}</ProtectedRoute>} />
      <Route path="/players" element={<ProtectedRoute>{() => withShell(<PlayerSearchPage />)}</ProtectedRoute>} />
      <Route path="/players/compare" element={<ProtectedRoute>{() => withShell(<PlayerComparePage />)}</ProtectedRoute>} />
      <Route path="/players/similarity" element={<ProtectedRoute>{() => withShell(<SimilarityPage />)}</ProtectedRoute>} />
      <Route path="/players/roles" element={<ProtectedRoute>{() => withShell(<RolesPage />)}</ProtectedRoute>} />
      <Route path="/players/:playerId" element={<ProtectedRoute>{() => withShell(<PlayerProfilePage />)}</ProtectedRoute>} />
      <Route path="/market" element={<ProtectedRoute>{() => withShell(<MarketPage variant="overview" />)}</ProtectedRoute>} />
      <Route path="/market/valuation" element={<ProtectedRoute>{() => withShell(<MarketPage variant="valuation" />)}</ProtectedRoute>} />
      <Route path="/market/opportunities" element={<ProtectedRoute>{() => withShell(<MarketPage variant="opportunities" />)}</ProtectedRoute>} />
      <Route path="/market/replacements" element={<ProtectedRoute>{() => withShell(<MarketPage variant="replacements" />)}</ProtectedRoute>} />
      <Route path="/market/risk" element={<ProtectedRoute>{() => withShell(<MarketPage variant="risk" />)}</ProtectedRoute>} />
      <Route path="/tactical/fit" element={<ProtectedRoute>{() => withShell(<TacticalFitPage />)}</ProtectedRoute>} />
      <Route path="/matches" element={<ProtectedRoute>{() => withShell(<MatchesPage />)}</ProtectedRoute>} />
      <Route path="/matches/:matchId" element={<ProtectedRoute>{() => withShell(<MatchesPage detail />)}</ProtectedRoute>} />
      <Route path="/squad/builder" element={<ProtectedRoute>{() => withShell(<SquadPage variant="builder" />)}</ProtectedRoute>} />
      <Route path="/squad/simulator" element={<ProtectedRoute>{() => withShell(<SquadPage variant="simulator" />)}</ProtectedRoute>} />
      <Route path="/squad/scenarios" element={<ProtectedRoute>{() => withShell(<SquadPage variant="scenarios" />)}</ProtectedRoute>} />
      <Route path="/research" element={<ProtectedRoute>{() => withShell(<ResearchPage variant="overview" />)}</ProtectedRoute>} />
      <Route path="/research/models" element={<ProtectedRoute>{() => withShell(<ResearchPage variant="models" />)}</ProtectedRoute>} />
      <Route path="/research/data" element={<ProtectedRoute>{() => withShell(<ResearchPage variant="data" />)}</ProtectedRoute>} />
      <Route path="/research/experiments" element={<ProtectedRoute>{() => withShell(<ResearchPage variant="experiments" />)}</ProtectedRoute>} />
      <Route path="/system/data-quality" element={<ProtectedRoute>{() => withShell(<DataQualityPage />)}</ProtectedRoute>} />
      <Route path="/copilot" element={<ProtectedRoute>{({ user }) => withShell(<CopilotPage user={user} />)}</ProtectedRoute>} />
      <Route path="/decisions" element={<ProtectedRoute>{() => withShell(<DecisionPage />)}</ProtectedRoute>} />
      <Route path="/decisions/recruitment" element={<ProtectedRoute>{() => withShell(<DecisionPage />)}</ProtectedRoute>} />
      <Route path="/decisions/replacement" element={<ProtectedRoute>{() => withShell(<DecisionPage />)}</ProtectedRoute>} />
      <Route path="/decisions/scenarios" element={<ProtectedRoute>{() => withShell(<DecisionPage />)}</ProtectedRoute>} />
      <Route path="/shortlists" element={<ProtectedRoute>{() => withShell(<ShortlistsPage />)}</ProtectedRoute>} />
      <Route path="/shortlists/:shortlistId" element={<ProtectedRoute>{() => withShell(<ShortlistsPage detail />)}</ProtectedRoute>} />
      <Route path="/recruitment/projects" element={<ProtectedRoute>{() => withShell(<RecruitmentProjectsPage />)}</ProtectedRoute>} />
      <Route path="/watchlists" element={<ProtectedRoute>{() => withShell(<WatchlistsPage />)}</ProtectedRoute>} />
      <Route path="/scenarios" element={<ProtectedRoute>{() => withShell(<ScenariosPage />)}</ProtectedRoute>} />
      <Route path="/operations" element={<ProtectedRoute>{() => withShell(<OperationsPage />)}</ProtectedRoute>} />
      <Route path="/operations/global" element={<ProtectedRoute>{() => withShell(<GlobalOperationsPage />)}</ProtectedRoute>} />
      <Route path="/intelligence/continuous" element={<ProtectedRoute>{() => withShell(<ContinuousIntelligencePage />)}</ProtectedRoute>} />
      <Route path="/decision-lab" element={<ProtectedRoute>{() => withShell(<DecisionLabPage />)}</ProtectedRoute>} />
      <Route path="/outcome-intelligence" element={<ProtectedRoute>{() => withShell(<OutcomeIntelligencePage />)}</ProtectedRoute>} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

function App() {
  return <div className="App"><BrowserRouter><AppRouter /></BrowserRouter></div>;
}

export default App;
