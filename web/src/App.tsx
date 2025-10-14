import NavBar from "./components/NavBar";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import PlannerPage from "./pages/PlannerPage";

const App = () => (
  <BrowserRouter>
    <div className="app-shell">
      <NavBar />
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/planner" element={<PlannerPage />} />
        </Routes>
      </main>
      <footer className="footer">
        <p>
          © {new Date().getFullYear()} AlpScheduler · Plan smarter, wander further.
        </p>
      </footer>
    </div>
  </BrowserRouter>
);

export default App;
