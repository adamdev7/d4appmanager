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
import { GoogleCallbackPage } from "@/pages/auth/GoogleCallbackPage";
import { DashboardPage } from "@/pages/dashboard/DashboardPage";
import { GeneralSettingsPage } from "@/pages/settings/GeneralSettingsPage";
import { StoresSettingsPage } from "@/pages/settings/StoresSettingsPage";
import { GmailSettingsPage } from "@/pages/settings/GmailSettingsPage";
import { EmailAutomationPage } from "@/pages/modules/EmailAutomationPage";
import { AIEmailAssistantPage } from "@/pages/modules/AIEmailAssistantPage";
import { ModulePlaceholderPage } from "@/pages/modules/ModulePlaceholderPage";
import { TrackingPage } from "@/pages/modules/TrackingPage";
import { AnalyticsPage } from "@/pages/modules/AnalyticsPage";
import { AdsPage } from "@/pages/modules/AdsPage";
import { MetaCapiPage } from "@/pages/modules/MetaCapiPage";
import { AIAdsLayout } from "@/pages/ai-ads/AIAdsLayout";
import { AIAdsDashboardPage } from "@/pages/ai-ads/AIAdsDashboardPage";
import { CreativesPage } from "@/pages/ai-ads/CreativesPage";
import { GeneratePage } from "@/pages/ai-ads/GeneratePage";
import { GenerationProgressPage } from "@/pages/ai-ads/GenerationProgressPage";
import { StrategyPage } from "@/pages/ai-ads/StrategyPage";
import { PerformancePage } from "@/pages/ai-ads/PerformancePage";
import { RecommendationsPage } from "@/pages/ai-ads/RecommendationsPage";
import { AIAdsSettingsPage } from "@/pages/ai-ads/AIAdsSettingsPage";
import { PrivacyPage } from "@/pages/legal/PrivacyPage";
import { TermsPage } from "@/pages/legal/TermsPage";
import { HomePage } from "@/pages/HomePage";

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <StoreProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/verify-email" element={<VerifyEmailPage />} />
              <Route path="/auth/google/callback" element={<GoogleCallbackPage />} />
              <Route path="/privacy" element={<PrivacyPage />} />
              <Route path="/terms" element={<TermsPage />} />

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
                <Route path="/modules/ads" element={<AdsPage />} />
                <Route path="/modules/meta-capi" element={<MetaCapiPage />} />
                <Route path="/modules/ai-ads" element={<Navigate to="/ai-ads" replace />} />
                <Route path="/ai-ads" element={<AIAdsLayout />}>
                  <Route index element={<AIAdsDashboardPage />} />
                  <Route path="creatives" element={<CreativesPage />} />
                  <Route path="generate" element={<GeneratePage />} />
                  <Route path="progress" element={<GenerationProgressPage />} />
                  <Route path="progress/:jobId" element={<GenerationProgressPage />} />
                  <Route path="strategy" element={<StrategyPage />} />
                  <Route path="performance" element={<PerformancePage />} />
                  <Route path="recommendations" element={<RecommendationsPage />} />
                  <Route path="settings" element={<AIAdsSettingsPage />} />
                </Route>
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
