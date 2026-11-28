import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import { AuthProvider, useAuth } from "./auth";
import Login from "./pages/Login";
import Projects from "./pages/Projects";
import ProjectDetail from "./pages/ProjectDetail";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import VerifyEmail from "./pages/VerifyEmail";
import Profile from "./pages/Profile";
import AccessDenied from "./pages/AccessDenied";
import Admin from "./pages/Admin";

const queryClient = new QueryClient();

function Protected({ children, adminOnly = false }) {
  const { token, isAdmin, user } = useAuth();
  const location = useLocation();
  if (!token) return <Navigate to="/login" replace />;
  // Wait for /auth/me/ before judging the role, otherwise admins flash a 403.
  if (adminOnly && !user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="font-mono text-xs uppercase tracking-widest text-slate-500">Checking access…</p>
      </div>
    );
  }
  if (adminOnly && !isAdmin) {
    return <Navigate to="/access-denied" replace state={{ from: location.pathname }} />;
  }
  return children;
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="/" element={<Protected><Projects /></Protected>} />
          <Route path="/projects/:id" element={<Protected><ProjectDetail /></Protected>} />
          <Route path="/profile" element={<Protected><Profile /></Protected>} />
          <Route path="/access-denied" element={<Protected><AccessDenied /></Protected>} />
          <Route path="/admin" element={<Protected adminOnly><Admin /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);
