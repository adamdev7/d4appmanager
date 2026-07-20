import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "@/context/ThemeContext";
import { AuthProvider } from "@/context/AuthContext";
import { StoreProvider } from "@/context/StoreContext";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoginPage } from "@/pages/auth/LoginPage";
import { RegisterPage } from "@/pages/auth/RegisterPage";
import { ForgotPasswordPage } from "@/pages/auth/ForgotPasswordPage";
import { VerifyEmailPage } from "@/pages/auth/VerifyEmailPage";
import { DashboardPage } from "@/pages/dashboard/DashboardPage";
import { GeneralSettingsPage } from "@/pages/settings/GeneralSettingsPage";
import { StoresSettingsPage } from "@/pages/settings/StoresSettingsPage";
import { GmailSettingsPage } from "@/pages/settings/GmailSettingsPage";
import { EmailAutomationPage } from "@/pages/modules/EmailAutomationPage";
import { AIEmailAssistantPage } from "@/pages/modules/AIEmailAssistantPage";
import { ModulePlaceholderPage } from "@/pages/modules/ModulePlaceholderPage";
import { TrackingPage } from "@/pages/modules/TrackingPage";
import { AnalyticsPage } from "@/pages/modules/AnalyticsPage";

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <StoreProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/verify-email" element={<VerifyEmailPage />} />

              <Route
                element={
                  <ProtectedRoute>
                    <DashboardLayout />
                  </ProtectedRoute>
                }
              >
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/settings" element={<GeneralSettingsPage />} />
                <Route path="/settings/stores" element={<StoresSettingsPage />} />
                <Route path="/settings/gmail" element={<GmailSettingsPage />} />
                <Route path="/modules/ai-email" element={<AIEmailAssistantPage />} />
                <Route path="/modules/email" element={<EmailAutomationPage />} />
                <Route path="/modules/tracking" element={<TrackingPage />} />
                <Route path="/modules/analytics" element={<AnalyticsPage />} />
                <Route path="/modules/:slug" element={<ModulePlaceholderPage />} />
              </Route>

              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </BrowserRouter>
        </StoreProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
