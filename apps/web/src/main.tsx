import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import "./index.css";
import { CommunityHome, CommunitySearch } from "./pages/Communities";
import { Dash, PublicDashboard } from "./pages/Dash";
import { IssueNew } from "./pages/IssueNew";
import { IssueDetail, IssueList } from "./pages/Issues";
import { MePage } from "./pages/Me";
import { NewsDetail, NewsList } from "./pages/News";
import { SurveyAnswer } from "./pages/SurveyAnswer";

const qc = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Navigate to="/news" replace />} />
            <Route path="/news" element={<NewsList />} />
            <Route path="/news/:id" element={<NewsDetail />} />
            <Route path="/community" element={<CommunityHome />} />
            <Route path="/community/:id" element={<CommunityHome />} />
            <Route path="/communities" element={<CommunitySearch />} />
            <Route path="/issues" element={<IssueList />} />
            <Route path="/issues/new" element={<IssueNew />} />
            <Route path="/issues/:id" element={<IssueDetail />} />
            <Route path="/dash" element={<Dash />} />
            <Route path="/d/:slug" element={<PublicDashboard />} />
            <Route path="/me" element={<MePage />} />
            <Route path="/surveys/:id" element={<SurveyAnswer />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
