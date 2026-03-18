import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import AskPage from "./pages/AskPage";
import TimelinePage from "./pages/TimelinePage";
import GraphPage from "./pages/GraphPage";
import StalenessPage from "./pages/StalenessPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<AskPage />} />
          <Route path="/timeline" element={<TimelinePage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/staleness" element={<StalenessPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
